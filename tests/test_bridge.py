import asyncio
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import pymysql
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from bridge import client
from bridge.catalog import ProtocolError
from bridge.v2 import Store, session
import test_bridge_v2

ROOT = Path(__file__).resolve().parents[1]
CONFIG = '''protocol_version = 2
character_guid = 23
server = "wss://example.org:38281"
slot = "Azeroth"
[database]
host = "127.0.0.1"
port = 3306
user = "wowpilago"
database = "acore_characters"
'''


class ConfigTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "bridge.toml"
        self.path.write_text(CONFIG)

    def test_config_reads_character_slot_and_optional_defaults(self):
        config = client.load_config(self.path)
        self.assertEqual(config["character_guid"], 23)
        self.assertEqual(config["database"]["port"], 3306)
        self.path.write_text(CONFIG.replace("protocol_version = 2\n", "").replace("port = 3306\n", ""))
        self.assertNotIn("port", client.load_config(self.path)["database"])

    def test_typed_settings_and_unknown_keys(self):
        cases = {
            "character_guid = 23": ["true", "-1", "0", str(2**32), '"1"', "1.0"],
            "protocol_version = 2": ["1", "true", "2.0", '"2"'],
            'slot = "Azeroth"': ['" "', "23", "false", "[]"],
            "port = 3306": ["true", "0", "65536", '"3306"', "1.0"],
            'host = "127.0.0.1"': ['" "', "1"],
            'user = "wowpilago"': ['""', "true"],
            'database = "acore_characters"': ['" "', "[]"],
        }
        for setting, values in cases.items():
            for value in values:
                with self.subTest(setting=setting, value=value):
                    self.path.write_text(CONFIG.replace(setting, setting.split(" = ")[0] + " = " + value))
                    with self.assertRaises(ValueError):
                        client.load_config(self.path)
        for text, message in [
            (CONFIG.replace("character_guid = 23\n", ""), "Missing config"),
            (CONFIG.replace('user = "wowpilago"\n', ""), "Missing database"),
            (CONFIG + 'password = "secret"\n', "WOWPILAGO_DB_PASSWORD"),
            (CONFIG + 'autocommit = false\n', "Unknown database"),
            ('legacy = true\n' + CONFIG, "Unknown config"),
            (CONFIG.split("[database]")[0] + 'database = "bad"\n', "TOML table"),
            ("slot = [", "Invalid value"),
        ]:
            with self.subTest(text=text):
                self.path.write_text(text)
                with self.assertRaisesRegex(ValueError, message):
                    client.load_config(self.path)
        for key in ("server", "slot", "database"):
            with self.subTest(missing=key):
                text = CONFIG.split("[database]")[0] if key == "database" else "\n".join(
                    line for line in CONFIG.splitlines() if not line.startswith(key + " ="))
                self.path.write_text(text)
                with self.assertRaisesRegex(ValueError, "Missing config"):
                    client.load_config(self.path)

    def test_server_url_boundary(self):
        for value in ('"http://example.org"', '"ws:///missing"', '"ws://user:pass@host"',
                      '"ws://@host"', '"ws://host:bad"', '"ws://host:65536"',
                      '"ws://host:0"', '"ws://host:"', '"ws://[broken"',
                      '"ws://host/#fragment"', '"ws://ho st"', "42", "false", "[]"):
            with self.subTest(value=value):
                self.path.write_text(CONFIG.replace('"wss://example.org:38281"', value))
                with self.assertRaisesRegex(ValueError, "server must"):
                    client.load_config(self.path)
        for url in ("ws://localhost", "wss://[::1]:38281/path?token=test"):
            self.path.write_text(CONFIG.replace("wss://example.org:38281", url))
            self.assertEqual(client.load_config(self.path)["server"], url)

    def test_main_calls_v2_and_closes_on_return_interrupt_and_failure(self):
        for failure in (None, KeyboardInterrupt(), ProtocolError("bad manifest"),
                        pymysql.OperationalError("database lost"), OSError("socket failed")):
            with self.subTest(failure=failure), patch.object(sys, "argv", ["bridge", str(self.path)]), \
                    patch.object(client.v2, "Store") as factory, \
                    patch.object(client.v2, "run", new_callable=AsyncMock, side_effect=failure) as run:
                if failure is not None and not isinstance(failure, KeyboardInterrupt):
                    with self.assertLogs("wowpilago", "ERROR"), self.assertRaises(SystemExit) as stopped:
                        client.main()
                    self.assertEqual(stopped.exception.code, 1)
                else:
                    client.main()
                config = client.load_config(self.path)
                factory.assert_called_once_with(config["database"], 23)
                run.assert_awaited_once_with(config, factory.return_value)
                factory.return_value.close.assert_called_once_with()

    def test_direct_script_dispatches_to_v2_and_closes(self):
        with patch.object(sys, "argv", ["bridge/client.py", str(self.path)]), \
                patch.object(client.v2, "Store") as factory, \
                patch.object(client.v2, "run", new_callable=AsyncMock) as run:
            runpy.run_path(str(ROOT / "bridge/client.py"), run_name="__main__")
        config = client.load_config(self.path)
        factory.assert_called_once_with(config["database"], 23)
        run.assert_awaited_once_with(config, factory.return_value)
        factory.return_value.close.assert_called_once_with()

    def test_startup_errors_do_not_run_or_close_uncreated_store(self):
        for failure in (ValueError("invalid config"), OSError("missing config"),
                        pymysql.OperationalError("connection refused")):
            with self.subTest(failure=failure), patch.object(sys, "argv", ["bridge", str(self.path)]), \
                    patch.object(client.v2, "Store", side_effect=failure) as factory, \
                    patch.object(client.v2, "run", new_callable=AsyncMock) as run, \
                    self.assertLogs("wowpilago", "ERROR"), self.assertRaises(SystemExit):
                client.main()
            run.assert_not_called()
            factory.return_value.close.assert_not_called()
        self.path.write_text("protocol_version = 1\n")
        with patch.object(sys, "argv", ["bridge", str(self.path)]), patch.object(client.v2, "Store") as factory, \
                self.assertLogs("wowpilago", "ERROR"), self.assertRaises(SystemExit):
            client.main()
        factory.assert_not_called()

    def test_direct_and_module_invocations_report_config_errors_without_traceback(self):
        for invocation in (["bridge/client.py"], ["-m", "bridge.client"]):
            for path, expected in ((self.path.with_name("missing.toml"), "No such file"),
                                   (self.path, "protocol_version")):
                self.path.write_text(CONFIG.replace("protocol_version = 2", "protocol_version = 1"))
                result = subprocess.run([sys.executable, *invocation, str(path)], cwd=ROOT,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(expected, result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_obsolete_scripts_refuse_without_touching_realm(self):
        for script in ("verify_delivery.py", "verify_inventory_edges.py"):
            result = subprocess.run([sys.executable, str(ROOT / "tests" / script), "ws://localhost:38282"],
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Protocol 1", result.stderr)
            self.assertIn("--v2-isolated", result.stderr)
            self.assertNotIn("Traceback", result.stderr)


class IsolatedRunnerTests(unittest.TestCase):
    def test_runner_requires_explicit_database_environment(self):
        import verify_delivery
        with patch.object(sys, "argv", ["verify_delivery.py", "--v2-isolated"]), \
                patch.dict(verify_delivery.os.environ, {}, clear=True), \
                patch.object(verify_delivery.subprocess, "run") as run, \
                self.assertRaisesRegex(SystemExit, "WOWPILAGO_TEST_DB_PORT"):
            verify_delivery.main()
        run.assert_not_called()

    def test_runner_propagates_test_failures(self):
        import verify_delivery
        for codes in ([7], [0, 9], [0, 0]):
            with self.subTest(codes=codes), \
                    patch.object(sys, "argv", ["verify_delivery.py", "--v2-isolated"]), \
                    patch.dict(verify_delivery.os.environ, {"WOWPILAGO_TEST_DB_PORT": "13317",
                                                           "WOWPILAGO_DB_PASSWORD": "test-only"}), \
                    patch.object(verify_delivery.subprocess, "run", side_effect=[
                        subprocess.CompletedProcess([], code) for code in codes]) as run, \
                    self.assertRaises(SystemExit) as stopped:
                verify_delivery.main()
            self.assertEqual(stopped.exception.code, codes[-1])
            self.assertEqual(run.call_count, len(codes))


@unittest.skipUnless(os.environ.get("WOWPILAGO_TEST_DB_PORT"), "Set WOWPILAGO_TEST_DB_PORT for isolated v2 database tests")
class AdditionalV2Tests(unittest.TestCase):
    # Reuse the real v2 database fixture, not the retired protocol implementation.
    setUpClass = classmethod(test_bridge_v2.BridgeV2Tests.setUpClass.__func__)
    tearDownClass = classmethod(test_bridge_v2.BridgeV2Tests.tearDownClass.__func__)
    setUp = test_bridge_v2.BridgeV2Tests.setUp
    execute = test_bridge_v2.BridgeV2Tests.execute

    def test_overlap_then_append_and_unknown_batch_is_atomic(self):
        self.store.receive(0, [self.item, self.item])
        self.store.receive(1, [self.item, self.item])
        self.assertEqual(self.execute("SELECT item_index FROM mod_archipelago_reward ORDER BY item_index"),
                         ((0,), (1,), (2,)))
        with self.assertRaises(ProtocolError):
            self.store.receive(3, [self.item, {**self.item, "item": 999}])
        self.assertEqual(self.execute("SELECT COUNT(*) FROM mod_archipelago_reward"), ((3,),))

    def test_flags_change_and_missing_character_are_rejected(self):
        self.store.receive(0, [self.item])
        with self.assertRaises(ProtocolError):
            self.store.receive(0, [{**self.item, "flags": 0}])
        with self.assertRaisesRegex(ProtocolError, "does not exist"):
            Store(self.database, 999, self.catalog)

    def test_websocket_reconnect_replays_without_reapplying_rewards(self):
        observed = []

        async def exercise():
            async def server(socket):
                await socket.send(json.dumps([{"cmd": "RoomInfo", "seed_name": "bridge-v2-seed"}]))
                observed.extend(json.loads(await socket.recv()))
                await socket.send(json.dumps([
                    {"cmd": "Connected", "team": 0, "slot": 1, "slot_data": self.raw,
                     "checked_locations": [], "missing_locations": sorted(self.store.manifest.checks)},
                    {"cmd": "ReceivedItems", "index": 0, "items": [self.item]},
                ]))
                self.assertEqual(json.loads(await socket.recv()), [{"cmd": "Sync"}])
                await socket.close()

            async with serve(server, "127.0.0.1", 0) as listener:
                config = {"server": f"ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}",
                          "slot": "Azeroth", "database": self.database}
                for attempt in range(2):
                    with self.assertRaises(ConnectionClosed):
                        await asyncio.wait_for(session(config, self.store), timeout=8)
                    self.store.status("disconnected")
                    self.assertEqual(self.execute("SELECT item_index,applied,applied_value FROM mod_archipelago_reward"),
                                     ((0, 1, 3),) if attempt else ((0, 0, 0),))
                    self.execute("UPDATE mod_archipelago_reward SET applied=1,applied_value=3")

        asyncio.run(exercise())
        self.assertEqual([packet["cmd"] for packet in observed], ["Connect", "Connect"])
        self.assertEqual(observed[0]["uuid"], observed[1]["uuid"])
        self.assertEqual(self.execute("SELECT applied,applied_value FROM mod_archipelago_reward"), ((1, 3),))

    def test_offline_queue_survives_store_close_and_reconnect(self):
        self.store.receive(0, [self.item])
        self.store.status("disconnected")
        self.store.close()
        reopened = Store(self.database, 31, self.catalog)
        self.addCleanup(reopened.close)
        reopened.bind("bridge-v2-seed", 0, 1, self.raw)
        self.assertTrue(reopened.receive(0, [self.item]))
        self.assertEqual(self.execute("SELECT item_index,applied FROM mod_archipelago_reward"), ((0, 0),))


if __name__ == "__main__":
    unittest.main()
