import asyncio
import copy
import json
import os
import secrets
import tempfile
from unittest.mock import patch
from pathlib import Path
import unittest

import pymysql
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from bridge.catalog import Catalog, ProtocolError, filter_profile
from bridge.v2 import Store, session

ROOT = Path(__file__).resolve().parents[1]


def manifest_fixture(catalog, seed="bridge-v2-seed", slot=1, legendary_count=2):
    profile = next(profile for profile in catalog.profiles if profile["race_id"] == profile["class_id"] == 1)
    sets = [entry for entry in catalog.documents["gear"]["sets"] if 1 in entry["class_ids"]][:3]
    featured_pieces = {piece for entry in sets for piece in entry["pieces"]}
    stock = [{"wow_id": item["wow_id"], "price": item["price"], "max_purchases": 1}
             for item in sorted(catalog.gear.values(), key=lambda item: item["wow_id"])
             if item["quality"] != 5 and 1 in item["allowable_classes"]
             and catalog.class_roles[1].intersection(item["roles"]) and item["wow_id"] not in featured_pieces][:60]
    legends = [item["wow_id"] for item in catalog.gear.values() if item["quality"] == 5 and 1 in item["allowable_classes"]][:legendary_count]
    allowed = {reward["ap_id"] for reward in catalog.generic}
    allowed.update(ability["ap_id"] for ability in catalog.abilities if ability["class_id"] == 1)
    allowed.update(919400000 + entry for entry in legends)
    raw = {"protocol_version": 2, "catalog_schema_version": 2, "catalog_version": catalog.version,
           "seed_name": seed, "slot": slot, "items_handling": 7, "profile": copy.deepcopy(profile),
           "options": {"character_race": 1, "character_class": 1, "quests": 1, "exploration": 1,
                       "dungeon_bosses": 1, "dungeon_completions": 1, "level_milestones": 1, "raids": 1,
                       "merchant_stock": 60, "featured_sets": 3, "set_piece_probability": 0, "legendary_count": legendary_count},
           "selected_checks": copy.deepcopy(filter_profile(catalog.checks, profile)),
           "rewards": {str(code): {"kind": catalog.definitions[code]["kind"], "value": catalog.definitions[code]["value"]}
                       for code in allowed}, "legendary_ids": legends,
           "merchant": {"stock": stock, "total_cost": sum(entry["price"] for entry in stock), "voucher_supply": 204,
                        "featured_sets": [{"set_id": entry["wow_id"], "pieces": sorted(entry["pieces"]), "rolled_pieces": []}
                                          for entry in sets], "overflow": 0, "overflow_policy": "uniform_sample_of_rolled_pieces"},
           "rules": {"starting_level": 1, "starting_cap": 10, "maximum_level": 80,
                     "victory": "server_confirmed_level_80", "victory_requires_expansions": False,
                     "raid_items": "filler_only", "equipment_level_bypass": "authorized_item_guid_only",
                     "talent_reservation_levels": list(range(15, 71, 5)), "xp_bank_next_level_percent": 50}}
    return raw


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog()

    def test_real_catalog_manifest_yields_typed_effects_and_stock(self):
        parsed = self.catalog.parse(manifest_fixture(self.catalog), "bridge-v2-seed", 1)
        self.assertEqual(parsed.rewards[919100001], ("level_cap", 10))
        self.assertEqual(parsed.rewards[919100002], ("outland", 1))
        self.assertEqual(parsed.rewards[919100012], ("riding", 2))
        self.assertEqual(parsed.rewards[919100032], ("vouchers", 3))
        self.assertEqual(parsed.rewards[919100040], ("bag", 21841))
        self.assertEqual(len(parsed.stock), 60)
        self.assertIn(919600080, parsed.checks)

    def test_legendary_count_matches_world_option_range(self):
        for count in (0, 4, 5, 10):
            with self.subTest(count=count):
                raw = manifest_fixture(self.catalog, legendary_count=count)
                parsed = self.catalog.parse(raw, "bridge-v2-seed", 1)
                self.assertEqual(sum(kind == "legendary" for kind, value in parsed.rewards.values()), count)
                self.assertEqual(len(set(raw["legendary_ids"])), count)
        with self.assertRaisesRegex(ProtocolError, "legendary count"):
            self.catalog.parse(manifest_fixture(self.catalog, legendary_count=11), "bridge-v2-seed", 1)

    def test_catalog_version_ignores_provenance_but_tracks_gameplay(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name, document in self.catalog.documents.items():
                (directory / f"{name}.json").write_text(json.dumps(document))
            checks = copy.deepcopy(self.catalog.documents["checks"])
            checks["provenance"] = {"runtime_revision": "a different build label"}
            (directory / "checks.json").write_text(json.dumps(checks))
            self.assertEqual(Catalog(directory).version, self.catalog.version)
            checks["checks"][0]["min_cap"] = 80
            (directory / "checks.json").write_text(json.dumps(checks))
            self.assertNotEqual(Catalog(directory).version, self.catalog.version)

    def test_profile_restrictions_propagate_through_quest_ancestors(self):
        orc = {"race_id": 2, "class_id": 1, "faction": "horde"}
        blood_elf = {"race_id": 10, "class_id": 2, "faction": "horde"}
        orc_keys = {check["key"] for check in filter_profile(self.catalog.checks, orc)}
        elf_keys = {check["key"] for check in filter_profile(self.catalog.checks, blood_elf)}
        self.assertNotIn("quest_9704", orc_keys)
        self.assertIn("quest_9704", elf_keys)
        for profile in self.catalog.profiles:
            selected = filter_profile(self.catalog.checks, profile)
            keys = {check["key"] for check in selected}
            self.assertTrue(all(set(check["prerequisites"]) <= keys for check in selected))

    def test_identity_rules_profile_and_allowlist_are_boundaries(self):
        for change in (lambda raw: raw.update(catalog_version="wrong"),
                       lambda raw: raw["profile"].update(class_id=6),
                       lambda raw: raw["rules"].update(victory_requires_expansions=True),
                       lambda raw: raw["rewards"]["919100020"].update(value=True),
                       lambda raw: raw.update(seed_name="another-room")):
            raw = manifest_fixture(self.catalog)
            change(raw)
            with self.assertRaises(ProtocolError):
                self.catalog.parse(raw, "bridge-v2-seed", 1)

    def test_stock_cannot_forge_price_duplicate_or_legendary(self):
        for mutation in (lambda raw: raw["merchant"]["stock"][0].update(price=0),
                         lambda raw: raw["merchant"]["stock"].__setitem__(1, raw["merchant"]["stock"][0]),
                         lambda raw: raw["merchant"]["stock"][0].update(wow_id=raw["legendary_ids"][0]),
                         lambda raw: raw["merchant"]["stock"][0].update(max_purchases=True)):
            raw = manifest_fixture(self.catalog)
            mutation(raw)
            with self.assertRaises(ProtocolError):
                self.catalog.parse(raw, "bridge-v2-seed", 1)

    def test_featured_piece_cannot_be_reintroduced_after_failed_roll(self):
        raw = manifest_fixture(self.catalog)
        piece = raw["merchant"]["featured_sets"][0]["pieces"][0]
        raw["merchant"]["stock"][0] = {"wow_id": piece, "price": self.catalog.gear[piece]["price"], "max_purchases": 1}
        raw["merchant"]["total_cost"] = sum(entry["price"] for entry in raw["merchant"]["stock"])
        with self.assertRaisesRegex(ProtocolError, "independent"):
            self.catalog.parse(raw, "bridge-v2-seed", 1)


@unittest.skipUnless(os.environ.get("WOWPILAGO_TEST_DB_PORT"), "Set WOWPILAGO_TEST_DB_PORT for isolated v2 bridge tests")
class BridgeV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = dict(host="127.0.0.1", port=int(os.environ["WOWPILAGO_TEST_DB_PORT"]), user="root",
                            database=f"wowpilago_bridge_v2_test_{os.getpid()}")
        options = {key: value for key, value in cls.database.items() if key != "database"}
        cls.db = pymysql.connect(**options, password=os.environ["WOWPILAGO_DB_PASSWORD"], autocommit=True)
        with cls.db.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{cls.database['database']}`")
            cursor.execute(f"USE `{cls.database['database']}`")
            cursor.execute("CREATE TABLE IF NOT EXISTS characters (guid INT UNSIGNED PRIMARY KEY,name VARCHAR(12),"
                           "account INT UNSIGNED NOT NULL,level TINYINT UNSIGNED NOT NULL,`class` TINYINT UNSIGNED NOT NULL,"
                           "race TINYINT UNSIGNED NOT NULL,online TINYINT UNSIGNED NOT NULL DEFAULT 0,xp INT UNSIGNED DEFAULT 0,"
                           "money INT UNSIGNED DEFAULT 0) ENGINE=InnoDB")
            cursor.execute("CREATE TABLE IF NOT EXISTS item_instance (guid INT UNSIGNED PRIMARY KEY) ENGINE=InnoDB")
            for statement in (ROOT / "sql/v2.sql").read_text().split(";"):
                if statement.strip():
                    cursor.execute(statement)
        cls.catalog = Catalog()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def execute(self, sql, args=()):
        with self.db.cursor() as cursor:
            cursor.execute(sql, args)
            return cursor.fetchall()

    def setUp(self):
        for table in ("mod_archipelago_authorized_item", "mod_archipelago_purchase", "mod_archipelago_stock",
                      "mod_archipelago_ability", "mod_archipelago_boss_credit", "mod_archipelago_check",
                      "mod_archipelago_allowed_reward", "mod_archipelago_enabled_check", "mod_archipelago_reward",
                      "mod_archipelago_progress", "mod_archipelago_binding", "characters"):
            self.execute(f"DELETE FROM {table}")
        self.execute("INSERT INTO characters (guid,name,account,level,`class`,race) VALUES (31,'V2Probe',1,1,1,1),(32,'V2Other',1,1,1,1)")
        self.raw = manifest_fixture(self.catalog)
        self.store = Store(self.database, 31, self.catalog)
        self.addCleanup(self.store.close)
        self.binding = self.store.bind("bridge-v2-seed", 0, 1, self.raw)
        self.item = {"class": "NetworkItem", "item": 919100032, "location": -2, "player": 0, "flags": 2}

    def test_persists_binding_and_all_personal_stock_once(self):
        self.assertEqual(self.execute("SELECT COUNT(*),SUM(sold) FROM mod_archipelago_stock"), ((60, 0),))
        self.execute("UPDATE mod_archipelago_stock SET sold=1 WHERE stock_index=0")
        self.execute("UPDATE mod_archipelago_progress SET vouchers=42")
        self.execute("UPDATE characters SET online=1 WHERE guid=31")
        self.store.bind("bridge-v2-seed", 0, 1, self.raw)
        self.assertEqual(self.execute("SELECT COUNT(*),SUM(sold) FROM mod_archipelago_stock"), ((60, 1),))
        self.assertEqual(self.execute("SELECT vouchers FROM mod_archipelago_progress"), ((42,),))
        changed = copy.deepcopy(self.raw)
        changed["merchant"]["stock"][0], changed["merchant"]["stock"][1] = changed["merchant"]["stock"][1], changed["merchant"]["stock"][0]
        with self.assertRaisesRegex(ProtocolError, "immutable"):
            self.store.bind("bridge-v2-seed", 0, 1, changed)

    def test_least_privilege_account_runs_bridge_but_cannot_modify_gameplay(self):
        user, password = f"wp_bridge_test_{os.getpid()}", secrets.token_hex(24)
        self.execute("CREATE USER %s@%s IDENTIFIED BY %s", (user, "%", password))
        self.addCleanup(self.execute, "DROP USER %s@%s", (user, "%"))
        permissions = (ROOT / "sql/bridge_permissions.sql").read_text()
        permissions = permissions.replace("acore_characters", self.database["database"])
        permissions = permissions.replace("'wowpilago_bridge'@'localhost'", f"'{user}'@'%%'")
        for statement in permissions.split(";"):
            if statement.strip():
                self.execute(statement)
        with patch.dict(os.environ, {"WOWPILAGO_DB_PASSWORD": password}):
            restricted = Store({**self.database, "user": user}, 32, self.catalog)
        self.addCleanup(restricted.close)
        binding = restricted.bind("restricted-seed", 0, 1, manifest_fixture(self.catalog, seed="restricted-seed"))
        self.assertTrue(restricted.receive(0, [self.item]))
        restricted.status("connected")
        check = self.raw["selected_checks"][0]["ap_id"]
        self.execute("INSERT INTO mod_archipelago_check (binding_id,location_id) VALUES (%s,%s)", (binding, check))
        self.assertEqual(restricted.pending_checks(), [check])
        restricted.checked([check], reset=True)
        self.assertEqual(restricted.pending_checks(), [])
        self.assertFalse(restricted.victory())
        with restricted.db.cursor() as cursor:
            for attack in ("UPDATE characters SET level=80", "UPDATE mod_archipelago_progress SET vouchers=999",
                           "UPDATE mod_archipelago_binding SET manifest=JSON_OBJECT()", "DELETE FROM mod_archipelago_reward",
                           "SELECT * FROM item_instance", "SELECT * FROM mod_archipelago_purchase"):
                with self.subTest(attack=attack), self.assertRaises(pymysql.err.OperationalError) as error:
                    cursor.execute(attack)
                self.assertIn(error.exception.args[0], (1142, 1143))

    def test_occupied_slot_and_character_rebinding_are_rejected(self):
        other = Store(self.database, 32, self.catalog)
        self.addCleanup(other.close)
        with self.assertRaises(pymysql.IntegrityError):
            other.bind("bridge-v2-seed", 0, 1, self.raw)
        with self.assertRaisesRegex(ProtocolError, "another seed"):
            self.store.bind("other-seed", 0, 1, manifest_fixture(self.catalog, seed="other-seed"))
        with self.assertRaisesRegex(ProtocolError, "Another bridge"):
            Store(self.database, 31, self.catalog)

    def test_first_binding_requires_offline_level_one(self):
        self.execute("UPDATE characters SET online=1 WHERE guid=32")
        other = Store(self.database, 32, self.catalog)
        self.addCleanup(other.close)
        with self.assertRaisesRegex(ProtocolError, "offline level-1"):
            other.bind("another-seed", 0, 1, manifest_fixture(self.catalog, seed="another-seed"))

    def test_received_indices_are_immutable_and_do_not_reapply(self):
        self.assertFalse(self.store.receive(2, [self.item]))
        self.assertTrue(self.store.receive(0, [self.item]))
        self.execute("UPDATE mod_archipelago_reward SET applied=1,applied_value=3")
        self.assertTrue(self.store.receive(0, [self.item]))
        self.assertEqual(self.execute("SELECT item_index,kind,value,applied,applied_value FROM mod_archipelago_reward"),
                         ((0, "vouchers", 3, 1, 3),))
        with self.assertRaises(ProtocolError):
            self.store.receive(0, [{**self.item, "player": 2}])
        with self.assertRaises(ProtocolError):
            self.store.receive(0, [])
        with self.assertRaises(ProtocolError):
            self.store.receive(1, [{**self.item, "item": 1}])

    def test_outbox_waits_for_ack_and_repairs_server_rollback(self):
        location = min(self.store.manifest.checks)
        self.execute("INSERT INTO mod_archipelago_check (binding_id,location_id) VALUES (%s,%s)", (self.binding, location))
        self.assertEqual(self.store.pending_checks(), [location])
        self.store.checked([location])
        self.assertEqual(self.store.pending_checks(), [])
        self.store.checked([], reset=True)
        self.assertEqual(self.store.pending_checks(), [location])
        with self.assertRaises(ProtocolError):
            self.store.checked([1])

    def test_cap_is_not_victory_and_deleted_character_keeps_history(self):
        self.execute("UPDATE mod_archipelago_progress SET cap_items=7,victory=1,last_level=80")
        self.assertFalse(self.store.victory())
        self.execute("UPDATE characters SET level=80 WHERE guid=31")
        self.assertTrue(self.store.victory())
        self.store.receive(0, [self.item])
        self.execute("DELETE FROM characters WHERE guid=31")
        with self.assertRaisesRegex(ProtocolError, "deleted"):
            self.store.ensure_active()
        self.store.status("disconnected")
        self.assertEqual(self.execute("SELECT character_guid,status FROM mod_archipelago_binding"), ((None, "archived"),))
        self.assertEqual(self.execute("SELECT COUNT(*) FROM mod_archipelago_reward"), ((1,),))

    def test_websocket_only_reports_native_checks_and_actual_victory(self):
        observed = []
        location = min(self.store.manifest.checks)

        async def exercise():
            async def server(socket):
                await socket.send(json.dumps([{"cmd": "RoomInfo", "seed_name": "bridge-v2-seed"}]))
                observed.extend(json.loads(await socket.recv()))
                await socket.send(json.dumps([{"cmd": "Connected", "team": 0, "slot": 1, "slot_data": self.raw,
                    "checked_locations": [], "missing_locations": sorted(self.store.manifest.checks)}]))
                observed.extend(json.loads(await socket.recv()))
                self.execute("INSERT INTO mod_archipelago_check (binding_id,location_id) VALUES (%s,%s)", (self.binding, location))
                await socket.send(json.dumps([{"cmd": "ReceivedItems", "index": 0, "items": [self.item]}]))
                observed.extend(json.loads(await socket.recv()))
                self.execute("UPDATE mod_archipelago_progress SET victory=1,last_level=80")
                self.execute("UPDATE characters SET level=80 WHERE guid=31")
                await socket.send(json.dumps([{"cmd": "RoomUpdate", "checked_locations": [location]}]))
                observed.extend(json.loads(await socket.recv()))
                await socket.close()
            async with serve(server, "127.0.0.1", 0) as listener:
                port = listener.sockets[0].getsockname()[1]
                with self.assertRaises(ConnectionClosed):
                    await asyncio.wait_for(session({"server": f"ws://127.0.0.1:{port}", "slot": "Azeroth",
                                                   "database": self.database}, self.store), timeout=8)
        asyncio.run(exercise())
        self.assertEqual([packet["cmd"] for packet in observed], ["Connect", "Sync", "LocationChecks", "StatusUpdate"])
        self.assertEqual(observed[2], {"cmd": "LocationChecks", "locations": [location]})
        self.assertEqual(observed[3], {"cmd": "StatusUpdate", "status": 30})
        self.assertEqual(self.store.pending_checks(), [])


if __name__ == "__main__":
    unittest.main()
