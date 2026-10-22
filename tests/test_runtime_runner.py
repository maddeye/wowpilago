"""Offline safety and literal wire/fixture checks. Never needs a running server."""

from contextlib import redirect_stdout
import io
import json
import struct
import unittest
from unittest.mock import MagicMock, Mock, patch

import verify_runtime as runtime
from realm_client import ProtocolError


class RuntimeRunnerTests(unittest.TestCase):
    def test_query_always_returns_rows_as_list_including_empty_mysql_tuple(self):
        runner = runtime.Runner.__new__(runtime.Runner)
        runner.db = MagicMock()
        cursor = runner.db.cursor.return_value.__enter__.return_value
        cursor.fetchall.side_effect = [(), [{'value': 1}]]
        self.assertEqual(runner.query('SELECT 1 WHERE FALSE'), [])
        self.assertEqual(runner.query('SELECT 1 AS value'), [{'value': 1}])
        with self.assertRaises(RuntimeError):
            runner.query('DELETE FROM characters')

    def account(self, **changes):
        row = dict(id=41, username="APV2A", email="wowpilago-fixture@invalid", security=0, online=0)
        return dict(row, **changes)

    def character(self, **changes):
        return dict(dict(guid=41, name="Apsfresh", account=12, race=1, **{"class": 1}), **changes)

    def test_default_and_setup_only_are_network_free_plans(self):
        for argv in ([], ["--setup"], ["--account", "APV2F"]):
            with self.subTest(argv=argv), patch.object(runtime.socket, "create_connection") as connect, \
                    patch.object(runtime, "authenticate") as authenticate, \
                    patch.object(runtime.Runner, "execute") as execute, \
                    patch.dict("sys.modules", {"pymysql": None, "bridge.v2": None}), \
                    redirect_stdout(io.StringIO()) as out:
                self.assertEqual(runtime.main(argv), 0)
                plan = json.loads(out.getvalue())
                self.assertFalse(plan["network_without_run"])
                self.assertEqual(plan["endpoints"], ["127.0.0.1:3724", "127.0.0.1:8085", "127.0.0.1:13317"])
                self.assertIn("NOT real AP client, gameplay, or release-gate", plan["label"])
                self.assertIn("nearby merchant positive purchase and replay/debit/equip", plan["remaining_live_gates"])
                connect.assert_not_called()
                authenticate.assert_not_called()
                execute.assert_not_called()

    def test_explicit_run_requires_test_only_password_before_network(self):
        for password in ("", "other"):
            with patch.dict(runtime.os.environ, {"WOWPILAGO_TEST_ACCOUNT_PASSWORD": password}, clear=True), \
                    patch.object(runtime.socket, "create_connection") as connect:
                with self.assertRaisesRegex(RuntimeError, "test-only"):
                    runtime.main(["--run"])
                connect.assert_not_called()

    def test_server_readiness_failure_precedes_sql_and_auth(self):
        with patch.dict(runtime.os.environ, {"WOWPILAGO_TEST_ACCOUNT_PASSWORD": "test-only", "WOWPILAGO_DB_PASSWORD": "private"}), \
                patch.object(runtime.socket, "create_connection", side_effect=ConnectionRefusedError), \
                patch.object(runtime, "authenticate") as authenticate, \
                patch.dict("sys.modules", {"pymysql": None}):
            with self.assertRaises(ConnectionRefusedError):
                runtime.main(["--run"])
            authenticate.assert_not_called()

    def test_all_six_marked_player_accounts_allowed(self):
        self.assertEqual(runtime.ACCOUNTS, ("APV2A", "APV2B", "APV2C", "APV2D", "APV2E", "APV2F"))
        for account in runtime.ACCOUNTS:
            runtime.guard_account(self.account(username=account), account)

    def test_unmarked_privileged_online_or_other_accounts_refused(self):
        for row, account in ((None, "APV2A"), (self.account(email="other"), "APV2A"),
                             (self.account(security=1), "APV2A"), (self.account(online=1), "APV2A"),
                             (self.account(username="TEST"), "TEST"), (self.account(), "APV2B")):
            with self.subTest(row=row), self.assertRaises(RuntimeError):
                runtime.guard_account(row, account)

    def test_test_account_only_has_explicit_setup_exception(self):
        runtime.guard_account(self.account(username="TEST", email="", security=3), "TEST", setup=True)
        for row, account in ((self.account(), "APV2A"), (self.account(username="TEST", security=0), "TEST")):
            with self.assertRaises(RuntimeError):
                runtime.guard_account(row, account, setup=True)

    def test_original_guids_refused_even_if_known(self):
        self.assertEqual(runtime.PROTECTED, {1, 2, 3})
        for guid in (1, 2, 3):
            with self.assertRaisesRegex(RuntimeError, "protected"):
                runtime.guard_character(self.character(guid=guid), 12, "Apsfresh", {guid})

    def test_only_known_created_owned_profile_allowed(self):
        runtime.guard_character(self.character(), 12, "Apsfresh", {41})
        for row, known in ((None, {41}), (self.character(), set()), (self.character(account=13), {41}),
                           (self.character(name="Other"), {41}), (self.character(race=2), {41}),
                           (self.character(**{"class": 2}), {41})):
            with self.assertRaises(RuntimeError):
                runtime.guard_character(row, 12, "Apsfresh", known)

    def test_explicit_profile_does_not_relax_default_human_warrior_guard(self):
        hunter = self.character(race=2, **{'class': 3})
        runtime.guard_character(hunter, 12, 'Apsfresh', {41},
                                expected_profile=dict(race_id=2, class_id=3))
        for row in (hunter, self.character(race=2), self.character(**{'class': 3})):
            with self.assertRaises(RuntimeError):
                runtime.guard_character(row, 12, 'Apsfresh', {41})
        for row in (self.character(race=1, **{'class': 3}), self.character(race=2, **{'class': 1})):
            sock = Mock()
            authorize = lambda guid, events: runtime.guard_character(
                row, 12, 'Apsfresh', {41}, expected_profile=dict(race_id=2, class_id=3))
            client = runtime.SmokeClient(sock, authorize)
            with self.assertRaisesRegex(RuntimeError, 'profile mismatch'):
                client.send(0x3D, struct.pack('<Q', 41))
            sock.sendall.assert_not_called()

    def test_test_profile_override_rejected_before_authentication(self):
        runner = object.__new__(runtime.Runner)
        with patch.object(runtime, 'authenticate') as auth:
            with self.assertRaisesRegex(RuntimeError, 'Human Warrior'), \
                 runner.login('TEST', guid=13, expected_profile=dict(race_id=2, class_id=3)):
                self.fail('Wrong GM profile entered')
            auth.assert_not_called()

    def test_login_requests_bounded_ready_wait_and_never_connects_without_ready_realm(self):
        runner = object.__new__(runtime.Runner)
        runner.names, runner.known = {41: 'Apsfresh'}, {41}
        runner.account_row = Mock(return_value=self.account(id=12))
        runner.character = Mock(return_value=self.character())
        with patch.dict(runtime.os.environ, {'WOWPILAGO_TEST_ACCOUNT_PASSWORD': 'test-only'}), \
                patch.object(runtime, 'authenticate', return_value=Mock(realms=[])) as auth, \
                patch.object(runtime.socket, 'create_connection') as connect:
            with self.assertRaisesRegex(RuntimeError, 'No ready unlocked realm'), \
                    runner.login('APV2A', guid=41):
                self.fail('No ready realm')
            auth.assert_called_once_with('APV2A', 'test-only', ready_timeout=45)
            connect.assert_not_called()

    def test_login_waits_offline_after_body_or_logout_failure(self):
        for failure in ('body', 'logout', 'connect'):
            with self.subTest(failure=failure):
                runner = object.__new__(runtime.Runner)
                runner.names, runner.known = {41: 'Apsfresh'}, {41}
                runner.account_row = Mock(return_value=self.account(id=12))
                runner.character = Mock(return_value=self.character())
                order = []
                runner.offline = Mock(side_effect=lambda _: order.append('offline'))
                client = Mock()
                client.connect.return_value = Mock(guid=41)
                if failure != 'body':
                    getattr(client, failure).side_effect = RuntimeError(failure)
                runner.client_type = Mock(return_value=client)
                realm = Mock(locked=False, flags=0)
                transport = MagicMock()
                transport.__exit__.side_effect = lambda *_: order.append('socket_closed')
                with patch.dict(runtime.os.environ, {'WOWPILAGO_TEST_ACCOUNT_PASSWORD': 'test-only'}), \
                     patch.object(runtime, 'authenticate', return_value=Mock(realms=[realm])), \
                     patch.object(runtime.socket, 'create_connection', return_value=transport):
                    with self.assertRaisesRegex(RuntimeError, failure):
                        with runner.login('APV2A', guid=41):
                            if failure == 'body':
                                raise RuntimeError('body')
                client.logout.assert_called_once()
                runner.offline.assert_called_once_with(41)
                self.assertEqual(order, ['socket_closed', 'offline'])

    def test_login_guard_runs_before_player_login_packet_is_sent(self):
        sock = Mock()
        client = runtime.SmokeClient(sock, Mock(side_effect=RuntimeError("not created")))
        with self.assertRaisesRegex(RuntimeError, "not created"):
            client.send(0x3D, struct.pack("<Q", 1))
        sock.sendall.assert_not_called()

    def test_command_is_say_common_not_addon_or_universal(self):
        self.assertEqual(runtime.say_packet(".archipelago buy 0"),
                         b"\x01\x00\x00\x00\x07\x00\x00\x00.archipelago buy 0\x00")
        self.assertEqual(runtime.say_packet(".archipelago equip 41 15"),
                         struct.pack("<II", 1, 7) + b".archipelago equip 41 15\0")
        for text in ("hello", ".save\0", ".save\n.levelup", "." * 255):
            with self.assertRaises(RuntimeError):
                runtime.say_packet(text)

    def test_player_selection_is_full_uint64_not_packed_guid(self):
        self.assertEqual(runtime.selection_packet(0x123456), b"\x56\x34\x12\0\0\0\0\0")
        for guid in (0, 1, 2, 3, -1, 2**32, True):
            with self.assertRaises(RuntimeError):
                runtime.selection_packet(guid)

    def test_setup_commands_are_supported_targeted_literals(self):
        self.assertEqual(runtime.bank_setup_commands("Apsfresh"), (
            ".learn 100", ".levelup Apsfresh 9", ".quest add 783 Apsfresh",
            ".quest complete 783 Apsfresh", ".quest reward 783 Apsfresh"))
        with self.assertRaises(ValueError):
            runtime.bank_setup_commands("Test;saveall")

    def test_current_manifest_is_valid_not_empty_or_handwritten_catalog_hash(self):
        catalog = runtime.Catalog()
        raw = runtime.manifest_fixture(catalog, "fabricated-native-smoke-unit")
        parsed = catalog.parse(raw, "fabricated-native-smoke-unit", 1)
        self.assertEqual(raw["catalog_version"], catalog.version)
        self.assertEqual(raw["profile"]["class_id"], 1)
        self.assertEqual(raw["profile"]["race_id"], 1)
        self.assertEqual(raw["legendary_ids"], [19019])
        self.assertEqual(len(parsed.stock), 30)
        self.assertGreater(len(parsed.checks), 0)
        self.assertEqual(parsed.rewards[919101100], ("ability", 100))
        self.assertEqual(parsed.rewards[919419019], ("legendary", 19019))

    def test_queue_arguments_are_exact_contiguous_fabricated_ingress(self):
        self.assertEqual(runtime.REWARDS, (919100001, 919100020, 919101100, 919100010,
                                           919100033, 919100040, 919419019))
        items = runtime.network_items()
        self.assertEqual(len(items), 7)
        self.assertEqual(items[0], {"class": "NetworkItem", "item": 919100001, "location": -1, "player": 0, "flags": 0})
        self.assertEqual([i["item"] for i in items], list(runtime.REWARDS))
        catalog = runtime.Catalog()
        manifest = catalog.parse(runtime.manifest_fixture(catalog, "fabricated-unit"), "fabricated-unit", 1)
        self.assertTrue(all(item["item"] in manifest.rewards for item in items))

    def test_system_chat_layout_and_truncation(self):
        packet = struct.pack("<BIQIQI", 0, 0, 0, 0, 0, 7) + b"cap 20\0\0"
        self.assertEqual(runtime.system_chat(packet), "cap 20")
        self.assertIsNone(runtime.system_chat(struct.pack("<BI", 7, 0xFFFFFFFF)))
        with self.assertRaises(ProtocolError):
            runtime.system_chat(packet[:-1])
        with self.assertRaises(ProtocolError):
            runtime.system_chat(packet + b"extra")

    def test_spell_layout_uses_uint32_spell_and_uint16_slot(self):
        packet = b"\0" + struct.pack("<H", 2) + struct.pack("<IHIH", 100, 0, 70000, 0) + struct.pack("<H", 1) + bytes(16)
        self.assertEqual(runtime.initial_spells(packet), {100, 70000})
        with self.assertRaises(ProtocolError):
            runtime.initial_spells(packet[:-1])

    def test_player_not_pet_talent_points_captured(self):
        client = runtime.SmokeClient(Mock(), Mock())
        client.process(0x4C0, b"\0" + struct.pack("<I", 1) + b"\1\0\0\6" + bytes(12))
        self.assertEqual(client.talent_points, 1)
        client.process(0x4C0, b"\1" + struct.pack("<I", 99))
        self.assertEqual(client.talent_points, 1)
        with self.assertRaises(RuntimeError):
            client.process(0x4C0, b"\0\1")

    def test_offline_waits_for_account_session_cleanup_too(self):
        runner = object.__new__(runtime.Runner)
        runner.character = Mock(return_value={"online": 0, "account": 41})
        runner.query = Mock(side_effect=[[{"online": 1}], [{"online": 0}]])
        with patch.object(runtime.time, "sleep") as sleep:
            self.assertEqual(runner.offline(41), {"online": 0, "account": 41})
        self.assertEqual(runner.query.call_count, 2)
        sleep.assert_called_once_with(0.2)

    def test_read_connection_refuses_mutation_and_multi_statements(self):
        runner = object.__new__(runtime.Runner)
        runner.db = Mock()
        for sql in ("UPDATE characters SET level=80", "DELETE FROM mod_archipelago_reward", "SELECT 1; DELETE FROM characters"):
            with self.assertRaises(RuntimeError):
                runner.query(sql)
        runner.db.cursor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
