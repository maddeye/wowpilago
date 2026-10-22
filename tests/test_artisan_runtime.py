"""Offline guards and packets only. No database, Docker calls, or authentication."""
from contextlib import redirect_stdout
import copy
import io
import json
import struct
import unittest
from unittest.mock import patch

import verify_artisan_runtime as artisan
from verify_runtime import MARKER
from integration_inputs import require_inputs


class ArtisanTests(unittest.TestCase):
    def test_preflight_checks_characters_not_agent_numbers(self):
        runner = artisan.ArtisanRunner.__new__(artisan.ArtisanRunner)
        runner.account_row = lambda account: {'id': 3}
        existing = [dict(guid=g, online=0) for g in (5, 7, 9)]
        for online in ([], [dict(guid=4)]):
            queries = []

            def query(sql, args=()):
                queries.append(sql)
                if '@@server_uuid' in sql:
                    return [dict(uuid=artisan.UUID)]
                if 'salt,verifier' in sql:
                    return [{}]
                if 'WHERE account=' in sql:
                    return existing
                self.assertIn('WHERE online<>0', sql)
                return online

            runner.query = query
            with patch.object(artisan, 'guard_account'), patch.object(artisan, 'check_account'), \
                 patch.dict(artisan.os.environ, WOWPILAGO_TEST_ACCOUNT_PASSWORD='fixture'), \
                 patch.object(artisan.travel, 'emit'):
                if online:
                    with self.assertRaisesRegex(RuntimeError, 'All characters must be offline'):
                        runner.preflight()
                else:
                    runner.preflight()
            self.assertFalse(any('40,46' in sql for sql in queries))

    def test_default_never_probes_or_authenticates(self):
        with patch.object(artisan, 'build_evidence', side_effect=AssertionError('probe')), \
             patch.object(artisan.shared, 'authenticate', side_effect=AssertionError('auth')), \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(artisan.main([]), 0)
        self.assertFalse(json.loads(output.getvalue())['network_without_run'])

    def test_incomplete_build_stops_before_docker_or_auth(self):
        with patch.object(artisan.Path, 'read_text', return_value='{"status":"building"}'), \
             patch.object(artisan, 'docker', side_effect=AssertionError('docker')), \
             patch.object(artisan.shared, 'authenticate', side_effect=AssertionError('auth')):
            with self.assertRaisesRegex(RuntimeError, 'not successful'):
                artisan.main(['--run'])

    def test_no_build_override(self):
        with redirect_stdout(io.StringIO()), patch('sys.stderr', io.StringIO()):
            with self.assertRaises(SystemExit):
                artisan.main(['--build', '/tmp/old'])

    def test_manifest_commit_image_and_source_pins(self):
        good = dict(status='success', core_commit=artisan.CORE, playerbots_commit=artisan.BOTS,
                    image_id=artisan.IMAGE, protocol_version=2,
                    module_files_sha256={'APProgression.cpp': artisan.CPP})
        for key in ('core_commit', 'playerbots_commit', 'image_id', 'protocol_version'):
            bad = copy.deepcopy(good)
            bad[key] = 'wrong'
            with self.subTest(key=key), patch.object(artisan.Path, 'read_text', return_value=json.dumps(bad)):
                with self.assertRaisesRegex(RuntimeError, 'commits/image/protocol'):
                    artisan.build_evidence()
        good['module_files_sha256']['APProgression.cpp'] = 'wrong'
        with patch.object(artisan.Path, 'read_text', return_value=json.dumps(good)):
            with self.assertRaisesRegex(RuntimeError, 'source hash'):
                artisan.build_evidence()

    def test_module_drift_stops_before_runtime(self):
        manifest = dict(status='success', core_commit=artisan.CORE, playerbots_commit=artisan.BOTS,
                        image_id=artisan.IMAGE, protocol_version=2,
                        module_files_sha256={'APProgression.cpp': artisan.CPP})
        with patch.object(artisan.Path, 'read_text', return_value=json.dumps(manifest)), \
             patch.object(artisan, 'fingerprints', return_value={'APProgression.cpp': 'drift'}):
            with self.assertRaisesRegex(RuntimeError, 'Module files differ'):
                artisan.build_evidence()

    def test_current_worktree_drift_is_rejected_before_runtime(self):
        require_inputs(artisan.BUILD / 'manifest.json')
        expected = json.loads((artisan.BUILD / 'manifest.json').read_text())['module_files_sha256']
        current = artisan.fingerprints(artisan.ROOT / 'src')
        with patch.object(artisan, 'docker', side_effect=AssertionError('runtime forbidden')):
            if current != expected:
                with self.assertRaisesRegex(RuntimeError, 'Module files differ'):
                    artisan.build_evidence()
            else:
                self.assertEqual(artisan.build_evidence()['module_files_sha256'], expected)

    def test_runtime_rejects_old_process_even_with_new_mount(self):
        info = dict(Id='owned', Image=artisan.IMAGE, State=dict(Running=True),
                    Config=dict(Labels={'com.docker.compose.project': 'wow-test',
                                        'com.docker.compose.service': 'worldserver'}),
                    Mounts=[dict(Destination='/work/install', RW=False,
                                 Source=str(artisan.BUILD / 'install'))])
        with patch.object(artisan, 'docker', side_effect=[json.dumps([info]), '6434b old']):
            with self.assertRaisesRegex(RuntimeError, 'mismatched runtime'):
                artisan.runtime_evidence(dict(world_sha256='a' * 64))

    def test_runtime_needs_parent_release_after_both_binary_checks(self):
        info = dict(Id='owned', Image=artisan.IMAGE, State=dict(Running=True),
                    Config=dict(Labels={'com.docker.compose.project': 'wow-test',
                                        'com.docker.compose.service': 'worldserver'}),
                    Mounts=[dict(Destination='/work/install', RW=False,
                                 Source=str(artisan.BUILD / 'install'))])
        world = 'a' * 64
        release = dict(owned_release=True, gui40_released=True, mail46_released=True, world_sha256=world)
        for valid in (False, True):
            value = dict(release, mail46_released=valid)
            with patch.object(artisan, 'docker', side_effect=[json.dumps([info]), world, world]), \
                 patch.object(artisan.Path, 'read_text', return_value=json.dumps(value)):
                if valid:
                    self.assertEqual(artisan.runtime_evidence(dict(world_sha256=world))['release'], release)
                else:
                    with self.assertRaisesRegex(RuntimeError, 'Parent release'):
                        artisan.runtime_evidence(dict(world_sha256=world))

    def test_receipts_append_only_and_contiguous(self):
        first = dict(item_index=0, ap_item=919100012, applied=1, immutable='old')
        last = dict(item_index=1, ap_item=artisan.ARTISAN, applied=1)
        codes = [first['ap_item'], last['ap_item']]
        artisan.guard_receipts([first, last], codes, [first])
        for rows in ([dict(first, immutable='changed'), last], [last],
                     [first, dict(last, item_index=2)], [first, dict(last, applied=0)],
                     [first, dict(last, ap_item=919100014)]):
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                artisan.guard_receipts(rows, codes, [first])

    def test_fresh_owner_marker_privilege_capacity_and_single_reservation(self):
        good = dict(id=3, username='APV2B', email=MARKER, security=0, online=0)
        for change in ({'username': 'APV2A'}, {'security': 3}, {'online': 1}, {'email': 'other'}, {'id': 1}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                artisan.FixtureOwner().reserve(dict(good, **change), 3)
        for count in (-1, 10, True):
            with self.assertRaises(RuntimeError):
                artisan.FixtureOwner().reserve(good, count)
        owner = artisan.FixtureOwner()
        owner.reserve(good, 3)
        with self.assertRaises(RuntimeError):
            owner.reserve(good, 3)

    def test_no_fresh_test_or_protected_relogin(self):
        runner = object.__new__(artisan.ArtisanRunner)
        runner.known, runner.guid = {13}, None
        for account, guid in (('TEST', None), ('APV2A', 4), ('APV2B', 24), ('TEST', 12)):
            with self.subTest(account=account, guid=guid), self.assertRaises(RuntimeError):
                with runner.login(account, guid=guid):
                    self.fail('unsafe login')

    def test_self_cast_packets_include_actual_fast_pair(self):
        for spell in artisan.MOUNTS:
            self.assertEqual(artisan.cast_packet(spell, 7), struct.pack('<BIBI', 7, spell, 0, 0))
        for spell, count in ((34091, 1), (54197, 1), (True, 1), (40192, 256), (32242, -1)):
            with self.assertRaises(RuntimeError):
                artisan.cast_packet(spell, count)

    def test_setup_never_trains_riding_or_changes_class(self):
        runner = object.__new__(artisan.ArtisanRunner)
        runner.guid, runner.names, runner.level = 99, {99: 'Apsabcdefghi'}, 60
        for command in ('.learn 34091', '.learn 54197', '.levelup Apsabcdefghi -1',
                        '.modify class 11', '.tele name Test Stormwind'):
            with self.subTest(command=command), self.assertRaises(RuntimeError):
                runner.setup(None, command)

    def test_complete_catalog_manifest_is_private_and_contains_artisan(self):
        catalog = artisan.Catalog()
        seed = 'private-fabricated-artisan-proof-offline-test'
        raw = artisan.manifest_fixture(catalog, seed)
        parsed = catalog.parse(raw, seed, 1)
        self.assertTrue(parsed.checksum)
        self.assertIn(str(artisan.ARTISAN), raw['rewards'])
        self.assertEqual((raw['profile']['race_id'], raw['profile']['class_id']), (1, 1))


if __name__ == '__main__':
    unittest.main()
