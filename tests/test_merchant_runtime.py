"""Offline guards and exact packets for the bounded merchant runner."""
from contextlib import nullcontext, redirect_stdout
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

import verify_merchant_runtime as merchant


class MerchantRuntimeTests(unittest.TestCase):
    def row(self, account='APV2D', **changes):
        return dict(dict(username=account, id=5, email='wowpilago-fixture@invalid',
                         security=3 if account == 'TEST' else 0, online=0), **changes)

    def test_default_is_offline_even_with_run_options(self):
        with patch.object(merchant, 'probe_source') as probe, \
                patch.object(merchant, 'released_class_result') as release, \
                patch.object(merchant.MerchantRunner, 'execute') as execute, \
                patch.dict('sys.modules', {'pymysql': None}), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(merchant.main(['--account', 'APV2F', '--peer', 'APV2D',
                                            '--reuse-control', 'class-systems-13']), 0)
            plan = json.loads(out.getvalue())
        self.assertFalse(plan['network_without_run'])
        self.assertIn('NOT real AP client', plan['label'])
        probe.assert_not_called()
        release.assert_not_called()
        execute.assert_not_called()

    def test_only_marked_gm0_independent_accounts(self):
        for account in merchant.ACCOUNTS:
            merchant.fixture_guard(account, self.row(account), 9)
        for account in ('APV2A', 'APV2B', 'APV2C', 'TEST', 'OTHER'):
            with self.subTest(account=account), self.assertRaises(RuntimeError):
                merchant.fixture_guard(account, self.row(account), 0)
        for change in ({'email': 'other'}, {'security': 1}, {'online': 1}):
            with self.assertRaises(RuntimeError):
                merchant.fixture_guard('APV2D', self.row(**change), 0)

    def test_setup_requires_offline_test_gm_and_free_slot(self):
        merchant.fixture_guard('TEST', self.row('TEST'), 8, setup=True)
        for account, row, count in [('TEST', self.row('TEST', online=1), 8),
                                    ('TEST', self.row('TEST', security=0), 8),
                                    ('TEST', self.row('TEST'), 10),
                                    ('APV2D', self.row(), 0)]:
            with self.subTest(account=account, count=count), self.assertRaises(RuntimeError):
                merchant.fixture_guard(account, row, count, setup=True)

    def test_release_requires_pass_and_offline_control(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'result.json'
            for result in ({}, {'result': {'event': 'FAIL', 'gm_guid': 13}, 'offline_fixture_guids': [13]},
                           {'result': {'event': 'PASS', 'gm_guid': 13}, 'offline_fixture_guids': [12]}):
                path.write_text(json.dumps(result))
                with self.assertRaises(RuntimeError):
                    merchant.released_class_result(path)
            path.write_text(json.dumps({'result': {'event': 'PASS', 'gm_guid': 13}, 'offline_fixture_guids': [12, 13]}))
            merchant.released_class_result(path)

    def test_run_refuses_credentials_and_same_account_before_probing(self):
        for args, env in [(['--run'], {}), (['--run', '--peer', 'APV2D'],
                                          {'WOWPILAGO_TEST_ACCOUNT_PASSWORD': 'test-only', 'WOWPILAGO_DB_PASSWORD': 'test-only'})]:
            with patch.dict(merchant.os.environ, env, clear=True), patch.object(merchant, 'probe_source') as probe:
                with self.assertRaises(RuntimeError):
                    merchant.main(args)
                probe.assert_not_called()

    def test_teleport_command_matches_pinned_command_tree(self):
        self.assertEqual(merchant.teleport_command('Apsabcdefghi'),
                         '.tele name npc guid Apsabcdefghi 9005000')
        for name in ('Test', 'Apjourney', 'Approbe', 'Apsabcdefghi 1', 'Apsabcd'):
            with self.assertRaises(RuntimeError):
                merchant.teleport_command(name)

    def test_literal_native_item_packet(self):
        self.assertEqual(merchant.equip_packet(131, 15), bytes.fromhex('83000000000000400f'))
        for guid, slot in ((0, 15), (2**32, 15), (True, 15), (131, -1), (131, 19)):
            with self.assertRaises(RuntimeError):
                merchant.equip_packet(guid, slot)

    def test_loaded_runtime_guid_not_spawn_counter(self):
        guid = (0xF130 << 48) | (900500 << 24) | 123
        text = f'DB GUID: 9005000, current GUID: GUID Full: 0x{guid:016x} Type: Creature Entry: 900500  Low: 123.'
        self.assertEqual(merchant.merchant_guid([text]), guid)
        self.assertEqual(merchant.npc_selection(guid), struct.pack('<Q', guid))
        for messages in ([text, text], ['(Not in world - showing DB data)', text], ['DB GUID: 1,' + text.split(',', 1)[1]]):
            with self.assertRaises(RuntimeError):
                merchant.merchant_guid(messages)
        for unsafe in (1, 2, 3, 4, 9005000, (0xF130 << 48) | (123 << 24) | 123):
            with self.assertRaises(RuntimeError):
                merchant.npc_selection(unsafe)

    def test_teleport_waits_for_native_async_position_commit(self):
        runner = object.__new__(merchant.MerchantRunner)
        runner.names = {17: 'Apsabcdefghi'}
        runner.offline, runner.setup = Mock(), Mock()
        runner.character = Mock(side_effect=[dict(map=0, position_x=0, position_y=0, position_z=0),
                                            dict(map=0, position_x=-8833.38, position_y=628.628, position_z=94.0066)])
        gm = Mock()
        runner.teleport(gm, 17)
        gm.stay.assert_called_once_with(.25)
        runner.setup.assert_called_once_with(gm, 17, '.tele name npc guid Apsabcdefghi 9005000')
        self.assertEqual(runner.character.call_count, 2)

    def test_teleport_commit_wait_is_bounded_and_checks_height(self):
        runner = object.__new__(merchant.MerchantRunner)
        runner.names = {17: 'Apsabcdefghi'}
        runner.offline, runner.setup = Mock(), Mock()
        runner.character = Mock(return_value=dict(map=0, position_x=-8833.38, position_y=628.628, position_z=0))
        with patch.object(merchant.time, 'monotonic', side_effect=[0, 0, 11]):
            with self.assertRaisesRegex(RuntimeError, 'within 10 seconds'):
                runner.teleport(Mock(), 17)

    def test_capture_keeps_existing_client_process_and_ping(self):
        client = Mock()
        original = client.process
        client.next_ping = 12345
        merchant.observe(client)
        with redirect_stdout(io.StringIO()):
            client.process(0x112, b'\x01')
            client.process(0x17D, struct.pack('<Q', 987))
            client.process(0x390, b'ping')
        self.assertEqual(client.equip_errors, [1])
        self.assertEqual(client.gossip, [987])
        self.assertEqual(original.call_count, 3)
        self.assertEqual(client.next_ping, 12345)
        with self.assertRaises(RuntimeError):
            client.process(0x112, b'')

    def test_login_rejects_protected_or_preexisting_guid_before_network(self):
        runner = object.__new__(merchant.MerchantRunner)
        runner.account, runner.peer, runner.known = 'APV2D', 'APV2E', {4, 99}
        for account, guid in [('APV2A', None), ('TEST', 1), ('APV2D', 4), ('APV2D', 10)]:
            with self.subTest(account=account, guid=guid), self.assertRaises(RuntimeError):
                with runner.login(account, guid=guid):
                    self.fail('Unsafe login accepted')

    def test_reuse_only_seeds_after_exact_prior_ownership_and_live_guards(self):
        runner = object.__new__(merchant.MerchantRunner)
        runner.known, runner.names = set(), {}
        runner.account_row = Mock(return_value=self.row('TEST', id=1))
        row = dict(guid=13, name='Apsjxsocfsik', account=1, race=1,
                   **{'class': 1}, level=1, online=0)
        runner.character = Mock(return_value=row)
        runner.query = Mock(return_value=[])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            evidence = {'summary.json': {'result': {'event': 'PASS', 'gm_guid': 13},
                                         'offline_fixture_guids': [13]},
                        'before.json': {'characters': [{'guid': 1, 'name': 'Test'}]}}
            for name, data in evidence.items():
                (path / name).write_text(json.dumps(data))
            event = dict(event='gm_fixture', guid=13, name='Apsjxsocfsik')
            (path / 'run.jsonl').write_text(json.dumps(event) + '\n')
            with patch.object(merchant, 'CONTROL_EVIDENCE', path), redirect_stdout(io.StringIO()) as out:
                failures = [('name', 'Other'), ('account', 2), ('race', 2), ('class', 2),
                            ('level', 2), ('online', 1), ('guid', 4)]
                for key, value in failures:
                    runner.character.return_value = dict(row, **{key: value})
                    with self.assertRaises(RuntimeError):
                        runner.reuse_control()
                    self.assertEqual(runner.known, set())
                runner.character.return_value = row
                runner.query.return_value = [{'id': 1}]
                with self.assertRaises(RuntimeError):
                    runner.reuse_control()
                runner.query.return_value = []
                (path / 'before.json').write_text(json.dumps({'characters': [row]}))
                with self.assertRaises(RuntimeError):
                    runner.reuse_control()
                (path / 'before.json').write_text(json.dumps(evidence['before.json']))
                (path / 'run.jsonl').write_text(json.dumps(dict(event, guid=19)))
                with self.assertRaises(RuntimeError):
                    runner.reuse_control()
                (path / 'run.jsonl').write_text((json.dumps(event) + '\n') * 2)
                with self.assertRaises(RuntimeError):
                    runner.reuse_control()
                (path / 'run.jsonl').write_text(json.dumps(event) + '\n')
                for changes in ({'security': 0}, {'online': 1}, {'id': 2}):
                    runner.account_row.return_value = self.row('TEST', **dict({'id': 1}, **changes))
                    with self.assertRaises(RuntimeError):
                        runner.reuse_control()
                runner.account_row.return_value = self.row('TEST', id=1)
                self.assertEqual(runner.known, set())
                self.assertEqual(runner.names, {})
                self.assertEqual(runner.reuse_control(), 13)
                self.assertEqual(runner.known, {13})
                self.assertEqual(runner.names, {13: 'Apsjxsocfsik'})
                hashes = json.loads(out.getvalue())['evidence_sha256']
                self.assertEqual(set(hashes), {'summary.json', 'before.json', 'run.jsonl'})
                self.assertTrue(all(len(value) == 64 for value in hashes.values()))

    def test_verified_control_login_passes_guid_not_creation_to_shared_runner(self):
        runner = object.__new__(merchant.MerchantRunner)
        runner.account, runner.peer = 'APV2D', 'APV2E'
        runner.known, runner.names = {13}, {13: 'Apsjxsocfsik'}
        runner.character = Mock(return_value={'account': 1})
        runner.account_row = Mock(return_value={'id': 1})
        with patch.object(merchant.Runner, 'login', return_value=nullcontext((Mock(), 13))) as login, \
                patch.object(merchant, 'observe'), redirect_stdout(io.StringIO()) as out:
            with runner.login('TEST', guid=13) as (_, guid):
                self.assertEqual(guid, 13)
        login.assert_called_once_with('TEST', guid=13)
        self.assertFalse(json.loads(out.getvalue())['fresh'])

    def test_funds_reuse_requires_pinned_creation_profile_and_binding(self):
        runner = object.__new__(merchant.MerchantRunner)
        runner.account, runner.peer = 'APV2D', 'APV2E'
        runner.known, runner.names = set(), {}
        runner.account_row = Mock(return_value=self.row('APV2E', id=6))
        profile = dict(guid=23, name=merchant.FUNDS_NAME, account=6, race=1,
                       **{'class': 1}, level=1, online=0)
        runner.character = Mock(return_value=profile)
        binding = dict(id=13, character_guid=23, character_name=merchant.FUNDS_NAME,
                       character_account=6, seed_name='owned-seed', class_id=1, race_id=1)
        runner.query = Mock(return_value=[binding])
        creation = dict(event='login', account='APV2E', fresh=True, guid=23, name=merchant.FUNDS_NAME)
        result = dict(event='PASS', peer=23, peer_binding=13)
        events = [creation, dict(event='fabricated_ingress', guid=23, binding=13,
                                account='APV2E', seed='owned-seed'), result]
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            (root / 'run').mkdir()
            path = root / 'run/run.jsonl'
            data = '\n'.join(json.dumps(e) for e in events).encode()
            digest = merchant.hashlib.sha256(data).hexdigest()
            path.write_bytes(data)
            (root / 'summary.json').write_text(json.dumps(dict(result=result, run_sha256=digest,
                                                              offline_fixture_guids=[23])))
            with patch.object(merchant, 'FUNDS_RUN', path), patch.object(merchant, 'FUNDS_HASH', digest):
                path.write_bytes(data + b'\n')
                with self.assertRaisesRegex(RuntimeError, 'hash'):
                    runner.reuse_funds_peer()
                path.write_bytes(data)
                for key, value in [('guid', 4), ('name', 'Other'), ('account', 1), ('race', 2),
                                   ('class', 2), ('level', 2), ('online', 1)]:
                    runner.character.return_value = dict(profile, **{key: value})
                    with self.assertRaises(RuntimeError):
                        runner.reuse_funds_peer()
                runner.character.return_value = profile
                for changes in ({'security': 1}, {'email': 'other'}, {'online': 1}, {'id': 5}):
                    runner.account_row.return_value = self.row('APV2E', **dict({'id': 6}, **changes))
                    with self.assertRaises(RuntimeError):
                        runner.reuse_funds_peer()
                runner.account_row.return_value = self.row('APV2E', id=6)
                runner.query.return_value = [dict(binding, character_guid=22)]
                with self.assertRaises(RuntimeError):
                    runner.reuse_funds_peer()
                self.assertEqual(runner.known, set())
                self.assertEqual(runner.names, {})
                runner.query.return_value = [binding]
                self.assertEqual(runner.reuse_funds_peer(), (23, 13))
                self.assertEqual(runner.known, {23})
                self.assertEqual(runner.names, {23: merchant.FUNDS_NAME})

    def test_funds_refusal_checks_free_space_native_reply_and_durable_economics(self):
        runner = object.__new__(merchant.MerchantRunner)
        runner.peer = 'APV2E'
        before = dict(progress=[{'vouchers': 4}], rewards=[], purchases=[], authorized=[],
                      stock=[dict(stock_index=1, item_entry=868, price=6, sold=0)],
                      inventory=[dict(bag=0, slot=23, item=1)], items=[dict(guid=1)])
        player = Mock(gossip=[merchant.FUNDS_NPC])
        player.command.return_value = ['Entry sold, invalid, or not enough vouchers.']
        runner.login = Mock(side_effect=lambda *a, **k: nullcontext((player, 23)))
        runner.query = Mock(return_value=[{'entry': 868}])
        with redirect_stdout(io.StringIO()):
            runner.saved = Mock(side_effect=[before, before])
            runner.insufficient_funds(23, 13, merchant.FUNDS_NPC)
            runner.login.assert_called_once_with('APV2E', guid=23)
            player.command.assert_called_once_with('.archipelago buy 1')
            for key, changed in [('progress', [{'vouchers': 3}]), ('purchases', [{'id': 1}]),
                                 ('stock', []), ('items', []), ('inventory', []), ('authorized', [{'id': 1}])]:
                runner.saved = Mock(side_effect=[before, dict(before, **{key: changed})])
                with self.assertRaisesRegex(RuntimeError, 'changed'):
                    runner.insufficient_funds(23, 13, merchant.FUNDS_NPC)
            runner.saved = Mock(return_value=dict(before, inventory=[dict(bag=0, slot=s) for s in range(23, 39)]))
            with self.assertRaisesRegex(RuntimeError, 'free backpack'):
                runner.insufficient_funds(23, 13, merchant.FUNDS_NPC)
            runner.saved = Mock(return_value=before)
            player.command.return_value = ['Purchase not completed.']
            with self.assertRaisesRegex(RuntimeError, 'refusal missing'):
                runner.insufficient_funds(23, 13, merchant.FUNDS_NPC)

    def test_observation_connection_rejects_writes(self):
        runner = object.__new__(merchant.MerchantRunner)
        runner.db = Mock()
        for sql in ('UPDATE characters SET level=80', 'CALL mod_archipelago_v2_purchase(1,0)', 'SELECT 1; DELETE FROM characters'):
            with self.assertRaises(RuntimeError):
                runner.query(sql)
        runner.db.cursor.assert_not_called()


if __name__ == '__main__':
    unittest.main()
