"""Offline guard checks only. No services, SQL or authentication."""
from contextlib import contextmanager
import io
import json
from pathlib import Path
import struct
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

import verify_dk_runtime as dk
from verify_runtime import MARKER
from integration_inputs import require_inputs


class DKTests(unittest.TestCase):
    def account(self):
        return dict(id=7, username='APV2F', email=MARKER, reg_mail=MARKER, security=0, online=0)

    def test_default_is_observation_free(self):
        with patch.object(dk, 'release') as release, patch.object(dk.artisan, 'build_evidence') as build, \
             patch.object(dk, 'DKRunner') as runner, patch.object(dk, 'source_evidence') as source, \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            dk.main([])
            self.assertEqual(json.loads(output.getvalue())['default_auth_calls'], 0)
            for method in (release, build, runner, source):
                method.assert_not_called()

    def test_real_pinned_source_contract_without_invented_setting(self):
        require_inputs(dk.artisan.ROOT / '.local/v2-realm/config/worldserver.conf',
                       dk.artisan.BUILD / 'source-files.sha256.json', dk.artisan.SOURCE,
                       dk.DBC_DIR / 'SkillLineAbility.dbc')
        evidence = dk.source_evidence()
        self.assertIsInstance(evidence, dict)
        self.assertNotIn('SkipDKintro', json.dumps(evidence))
        self.assertEqual(evidence['expected_start'], dict(
            race=1, class_id=6, level=55, map=609, zone=4298, talent_points=0,
            starting_spells=[6603, 48266, 47541]))
        self.assertEqual(evidence['config'], {'StartHeroicPlayerLevel': 55, 'PlayerStart.CustomSpells': 0})
        self.assertEqual(set(evidence['providers']), {6603, 48266, 47541})
        self.assertTrue(all(evidence['providers'].values()))
        self.assertTrue(all(len(h) == 64 for h in evidence['source_files_sha256'].values()))

    def test_source_contract_rejects_wrong_config_map_and_script_facts(self):
        require_inputs(dk.artisan.ROOT / '.local/v2-realm/config/worldserver.conf',
                       dk.artisan.BUILD / 'source-files.sha256.json', dk.artisan.SOURCE,
                       dk.DBC_DIR / 'SkillLineAbility.dbc')
        evidence = dk.source_evidence()
        inventory = json.loads((dk.artisan.BUILD / 'source-files.sha256.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, build = root / 'source', root / 'build'
            build.mkdir()
            for path in evidence['source_files_sha256']:
                target = source / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(dk.artisan.SOURCE / path, target)
            config = root / '.local/v2-realm/config/worldserver.conf'
            config.parent.mkdir(parents=True)
            normal = 'StartHeroicPlayerLevel = 55\nPlayerStart.CustomSpells = 0\n'
            config.write_text(normal)
            manifest = build / 'source-files.sha256.json'
            manifest.write_text(json.dumps(inventory))
            with patch.object(dk.artisan, 'ROOT', root), patch.object(dk.artisan, 'BUILD', build), \
                 patch.object(dk.artisan, 'SOURCE', source):
                self.assertEqual(dk.source_evidence()['expected_start'], evidence['expected_start'])
                for wrong in (normal.replace('55', '58'), normal.replace('= 0', '= 1')):
                    config.write_text(wrong)
                    with self.assertRaises(RuntimeError):
                        dk.source_evidence()
                config.write_text(normal)
                for path, before, after in (
                    ('data/sql/base/db_world/playercreateinfo.sql', '(1,6,609,4298,', '(1,6,0,12,'),
                    ('src/server/game/Entities/Player/Player.cpp',
                     'GetLevel() < 56 ? 0 : GetLevel() - 55', 'GetLevel() < 56 ? 46 : GetLevel() - 55'),
                    ('src/server/game/Handlers/CharacterHandler.cpp',
                     'sScriptMgr->OnPlayerCreate(newChar.get());', 'ChangedCreateHook();'),
                ):
                    target = source / path
                    original = target.read_text()
                    self.assertIn(before, original)
                    target.write_text(original.replace(before, after))
                    with self.subTest(path=path), self.assertRaisesRegex(RuntimeError, 'helper changed'):
                        dk.source_evidence()
                    # Even a matching fixture inventory must not excuse wrong domain facts.
                    manifest.write_text(json.dumps(dict(inventory, **{path: dk.artisan.digest(target)})))
                    with self.subTest(path=path), self.assertRaisesRegex(RuntimeError, 'source contract changed'):
                        dk.source_evidence()
                    target.write_text(original)
                    manifest.write_text(json.dumps(inventory))

    def test_eligibility_fails_closed(self):
        dk.eligibility(self.account(), [dict(level=77, **{'class': 1})])
        for rows in (None, [], [dict(level=54, **{'class': 1})],
                     [dict(level=55, **{'class': 6})], [dict(level=77)],
                     [dict(level=77, **{'class': 1})] * 10):
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                dk.eligibility(self.account(), rows)
        for field, value in (('id', 1), ('security', 3), ('reg_mail', 'wrong'), ('online', 1)):
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                dk.eligibility(dict(self.account(), **{field: value}), [dict(level=77, **{'class': 1})])

    def test_release_missing_expired_wrong_or_not_explicit(self):
        good = dict(native_matrix_released=True, owned_release=True, world_sha256=dk.WORLD,
                    manifest_sha256=dk.MANIFEST, account='APV2F', creation_limit=1,
                    issued_at=100, expires_at=1900)
        with tempfile.TemporaryDirectory() as directory, patch.object(dk, 'OUTPUT', Path(directory)):
            with self.assertRaises(FileNotFoundError):
                dk.release(101)
            path = Path(directory) / 'parent-release.json'
            path.write_text(json.dumps(good))
            dk.release(101)
            for change in (dict(native_matrix_released=False), dict(world_sha256='wrong'),
                           dict(expires_at=2000), dict(creation_limit=2), dict(issued_at=200)):
                path.write_text(json.dumps(dict(good, **change)))
                with self.assertRaises(RuntimeError):
                    dk.release(101)
            path.write_text(json.dumps(good))
            with self.assertRaises(RuntimeError):
                dk.release(1900)

    def owner(self):
        owner = Mock(guid=None, before={1, 2, 3, 4, 24}, create_sent=True, pending_name='Apsfresh',
                     selfcast=True, cast_sent=False)
        owner.observed = set()
        owner.character.return_value = dict(guid=40, account=7, name='Apsfresh', race=1,
                                           **{'class': 6}, level=55, online=0)
        return owner

    def test_first_login_requires_creation_event_and_actual_profile(self):
        owner = self.owner()
        authorize = Mock()
        client = dk.DKClient(Mock(), authorize, owner)
        with patch.object(dk, 'save'):
            for field, value in (('class', 1), ('race', 2), ('account', 1), ('level', 1), ('guid', 24)):
                original = owner.character.return_value
                owner.character.return_value = dict(original, **{field: value})
                with self.subTest(field=field), self.assertRaises(RuntimeError):
                    client.authorize_login(40, ['CREATED Apsfresh'])
                owner.character.return_value = original
            with self.assertRaises(RuntimeError):
                client.authorize_login(40, [])
            authorize.assert_not_called()
            client.authorize_login(40, ['CREATED Apsfresh'])
            authorize.assert_called_once()

    def test_creation_once_and_exact_selfcast_allowlist(self):
        owner = self.owner()
        owner.create_sent = False
        client = dk.DKClient(Mock(), Mock(), owner)
        with patch.object(dk.SmokeClient, 'send'), patch.object(dk, 'save'):
            with self.assertRaises(RuntimeError):
                client.send(0x36, dk.create_character('Apsfresh', race=1, class_id=1))
            packet = dk.create_character('Apsfresh', race=1, class_id=6)
            client.send(0x36, packet)
            with self.assertRaises(RuntimeError):
                client.send(0x36, packet)
            for opcode in (0x95, 0x13D, 0x10E, 0x0DC):
                with self.assertRaises(RuntimeError):
                    client.send(opcode)
            packet = struct.pack('<BIBI', 1, 48266, 0, 0)
            with self.assertRaises(RuntimeError):
                client.send(0x12E, packet)
            client.spells = {48266}
            for wrong in (struct.pack('<BIBI', 1, 47541, 0, 0), packet + b'\0'):
                with self.assertRaises(RuntimeError):
                    client.send(0x12E, wrong)
            client.send(0x12E, packet)
            with self.assertRaises(RuntimeError):
                client.send(0x12E, packet)

    def test_native_zero_talent_points_is_not_missing(self):
        client = dk.DKClient(Mock(), Mock(), self.owner())
        client.process(0x4C0, b'\0' + struct.pack('<I', 0) + b'\1\0')
        self.assertEqual(client.talent_points, 0)
        self.assertIn('0x4c0', client.raw)
        with self.assertRaises(RuntimeError):
            client.process(0x4C0, b'\0\0')

    def test_exception_waits_offline_even_before_shared_yield(self):
        runner = object.__new__(dk.DKRunner)
        runner.guid, runner.known, runner.before, runner.observed = 40, {40}, {24}, {40}
        runner.query = Mock(return_value=[dict(guid=24), dict(guid=40)])
        runner.offline = Mock()
        runner.all_offline = Mock()

        @contextmanager
        def broken(*args, **kwargs):
            raise RuntimeError('connect failed after creation')
            yield

        with patch.object(dk, 'release'), patch.object(dk.Runner, 'login', broken):
            with self.assertRaisesRegex(RuntimeError, 'connect failed'):
                with runner.login('APV2F', guid=40):
                    self.fail('must not yield')
        runner.offline.assert_called_once_with(40)
        with self.assertRaises(RuntimeError):
            with runner.login('TEST', guid=40):
                self.fail('TEST must never authenticate')

    def test_body_exception_also_waits_offline(self):
        runner = object.__new__(dk.DKRunner)
        runner.guid, runner.known, runner.before, runner.observed = 40, {40}, {24}, {40}
        runner.query = Mock(return_value=[dict(guid=40)])
        runner.offline, runner.all_offline = Mock(), Mock()

        @contextmanager
        def connected(*args, **kwargs):
            yield Mock(), 40

        with patch.object(dk, 'release'), patch.object(dk.Runner, 'login', connected):
            with self.assertRaisesRegex(RuntimeError, 'packet validation'):
                with runner.login('APV2F', guid=40):
                    raise RuntimeError('packet validation')
        runner.offline.assert_called_once_with(40)

    def test_failed_preflight_never_creates_or_authenticates(self):
        runner = object.__new__(dk.DKRunner)
        runner.reserved = False
        runner.all_offline = Mock()
        runner.preflight = Mock(side_effect=RuntimeError('ineligible'))
        with patch.object(dk, 'release'), patch.object(dk.Runner, 'login') as login:
            with self.assertRaisesRegex(RuntimeError, 'ineligible'):
                with runner.login('APV2F'):
                    self.fail('must not yield')
            login.assert_not_called()
            self.assertFalse(runner.reserved)

    def test_protected_population_excludes_only_new_dk(self):
        runner = object.__new__(dk.DKRunner)
        runner.before = {1, 4, 13, 24, 39}
        runner.query = Mock(return_value=[])
        tables = dict(characters=[dict(guid=g) for g in (1, 4, 13, 24, 39, 40)],
                      character_stats=[dict(guid=24), dict(guid=40)],
                      mod_archipelago_reward=[dict(binding_id=39, applied=0)])
        with patch.object(dk.CrashRunner, 'protected', return_value=tables):
            result = runner.protected()
        self.assertEqual([r['guid'] for r in result['characters']], [1, 4, 13, 24, 39])
        self.assertEqual(result['character_stats'], [dict(guid=24)])
        self.assertEqual(result['mod_archipelago_reward'], [dict(binding_id=39, applied=0)])

    def test_catalog_api_rejects_without_store(self):
        self.assertIn('Death Knights are excluded', dk.excluded())

    def test_missing_release_stops_before_preflight_or_auth(self):
        runner = object.__new__(dk.DKRunner)
        runner.preflight, runner.all_offline = Mock(), Mock()
        with patch.object(dk, 'release', side_effect=RuntimeError('no release')), \
             patch.object(dk.Runner, 'login') as login:
            with self.assertRaisesRegex(RuntimeError, 'no release'):
                with runner.login('APV2F'):
                    self.fail('must not yield')
            runner.preflight.assert_not_called()
            login.assert_not_called()


if __name__ == '__main__':
    unittest.main()
