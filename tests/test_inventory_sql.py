import os
from pathlib import Path
import threading
import time
import unittest

import pymysql


SQL = Path(__file__).resolve().parents[1] / "sql"


@unittest.skipUnless(os.environ.get("WOWPILAGO_TEST_DB_PORT"),
                     "Set WOWPILAGO_TEST_DB_PORT for isolated MySQL tests")
class InventorySqlTests(unittest.TestCase):
    @classmethod
    def connect(cls):
        return pymysql.connect(
            host="127.0.0.1", port=int(os.environ["WOWPILAGO_TEST_DB_PORT"]),
            user="root", password=os.environ["WOWPILAGO_DB_PASSWORD"],
            database="wowpilago_test", autocommit=True,
        )

    @classmethod
    def setUpClass(cls):
        cls.db = cls.connect()
        cls.addClassCleanup(cls.db.close)
        with cls.db.cursor() as cursor:
            cursor.execute("CREATE TABLE IF NOT EXISTS characters (guid INT UNSIGNED PRIMARY KEY)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS item_instance (
                    guid INT UNSIGNED NOT NULL DEFAULT 0 PRIMARY KEY,
                    itemEntry INT UNSIGNED DEFAULT 0,
                    owner_guid INT UNSIGNED NOT NULL DEFAULT 0,
                    creatorGuid INT UNSIGNED NOT NULL DEFAULT 0,
                    giftCreatorGuid INT UNSIGNED NOT NULL DEFAULT 0,
                    count INT UNSIGNED NOT NULL DEFAULT 1,
                    duration INT NOT NULL DEFAULT 0,
                    charges TINYTEXT,
                    flags INT UNSIGNED DEFAULT 0,
                    enchantments TEXT NOT NULL,
                    randomPropertyId SMALLINT NOT NULL DEFAULT 0,
                    durability SMALLINT UNSIGNED NOT NULL DEFAULT 0,
                    playedTime INT UNSIGNED NOT NULL DEFAULT 0,
                    text TEXT,
                    KEY idx_owner_guid (owner_guid)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS character_inventory (
                    guid INT UNSIGNED NOT NULL DEFAULT 0,
                    bag INT UNSIGNED NOT NULL DEFAULT 0,
                    slot TINYINT UNSIGNED NOT NULL DEFAULT 0,
                    item INT UNSIGNED NOT NULL DEFAULT 0 PRIMARY KEY,
                    UNIQUE KEY guid (guid, bag, slot),
                    KEY idx_guid (guid)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            for statement in (SQL / "characters.sql").read_text().split(";"):
                if statement.strip():
                    cursor.execute(statement)
            # inventory.sql uses exactly one $$ routine block, not arbitrary SQL delimiters.
            before, routine = (SQL / "inventory.sql").read_text().split("DELIMITER $$\n")
            cursor.execute(before.strip().removesuffix(";"))
            body, after = routine.split("$$\nDELIMITER ;")
            assert not after.strip()
            cursor.execute(body)

    def execute(self, sql, args=()):
        with self.db.cursor() as cursor:
            cursor.execute(sql, args)
            return cursor.fetchall()

    def clean(self):
        for table in ("mod_archipelago_delivery", "mod_archipelago_item",
                      "mod_archipelago_session", "character_inventory"):
            self.execute(f"DELETE FROM {table} WHERE guid IN (900001, 900002, 900003)")
        self.execute("DELETE FROM item_instance WHERE guid BETWEEN 910001 AND 910009")
        self.execute("DELETE FROM characters WHERE guid IN (900001, 900002, 900003)")

    def setUp(self):
        self.clean()
        self.addCleanup(self.clean)
        self.execute("INSERT INTO characters (guid) VALUES (900001), (900002)")
        self.execute("""
            INSERT INTO mod_archipelago_session (guid, seed_name, team, slot)
            VALUES (900001, 'inventory-sql-test', 0, 1),
                   (900003, 'inventory-sql-test', 0, 3)
        """)
        self.execute("""
            INSERT INTO mod_archipelago_item
                (guid, item_index, ap_item, location_id, sender, flags, item_entry)
            VALUES (900001, 0, 919000001, -2, 0, 1, 118),
                   (900003, 0, 919000001, -2, 0, 1, 118)
        """)

    def call(self, *, db=None, guid=900001, index=0, item=910001,
             bag=0, bag_slot=255, slot=23):
        with (db or self.db).cursor() as cursor:
            cursor.execute("CALL mod_archipelago_deliver(" + ",".join(["%s"] * 16) + ")", (
                guid, index, item, bag, bag_slot, slot, 123, 456, -7,
                "-1 2 0 0 0 ", 8, "1 2 3 " * 12, -9, 10, 11, "Potion's text",
            ))
            self.assertIsNone(cursor.description)
            while cursor.nextset():
                self.assertIsNone(cursor.description)

    def state(self, guid=900001):
        queue = self.execute("SELECT item_index, delivered FROM mod_archipelago_item WHERE guid=%s", (guid,))
        receipt = self.execute("SELECT item_index FROM mod_archipelago_delivery WHERE guid=%s", (guid,))
        inventory = self.execute("SELECT bag, slot, item FROM character_inventory WHERE guid=%s ORDER BY slot", (guid,))
        items = self.execute("SELECT guid, itemEntry, count FROM item_instance WHERE owner_guid=%s ORDER BY guid", (guid,))
        return queue, receipt, inventory, items

    def assert_pending(self):
        self.assertEqual(self.state(), (((0, 0),), (), (), ()))

    def insert_item(self, item=910003, owner=900001):
        self.execute("INSERT INTO item_instance (guid, owner_guid, enchantments) VALUES (%s, %s, '')", (item, owner))

    def equip_bag(self, owner=900001, slot=19):
        self.insert_item(owner=owner)
        self.execute("INSERT INTO character_inventory VALUES (900001, 0, %s, 910003)", (slot,))

    def test_success_persists_every_field_and_replay_ignores_new_candidate(self):
        self.call()
        self.assertEqual(self.state(), (
            ((0, 1),), ((0,),), ((0, 23, 910001),), ((910001, 118, 1),),
        ))
        self.assertEqual(self.execute("SELECT * FROM item_instance WHERE guid=910001"), ((
            910001, 118, 900001, 123, 456, 1, -7, "-1 2 0 0 0 ", 8,
            "1 2 3 " * 12, -9, 10, 11, "Potion's text",
        ),))
        before = self.state()
        self.call(item=910002, slot=24)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.execute("SELECT guid FROM item_instance WHERE guid=910002"), ())
        with self.connect() as observer:
            with observer.cursor() as cursor:
                cursor.execute("SELECT delivered FROM mod_archipelago_item WHERE guid=900001")
                self.assertEqual(cursor.fetchall(), ((1,),))

    def test_core_empty_transaction_wrapper(self):
        self.db.begin()
        self.call()
        self.db.commit()
        self.assertEqual(self.state(), (
            ((0, 1),), ((0,),), ((0, 23, 910001),), ((910001, 118, 1),),
        ))

    def test_occupied_slot_stays_pending_and_can_retry(self):
        self.insert_item()
        self.execute("INSERT INTO character_inventory VALUES (900001, 0, 23, 910003)")
        before = self.state()
        self.call()
        self.assertEqual(self.state(), before)
        self.call(slot=24)
        self.assertEqual(self.state(), (
            ((0, 1),), ((0,),), ((0, 23, 910003), (0, 24, 910001)),
            ((910001, 118, 1), (910003, 0, 1)),
        ))

    def test_absent_reward_creates_nothing(self):
        with self.assertRaisesRegex(pymysql.MySQLError, "Queued reward does not exist"):
            self.call(index=1)
        self.assert_pending()
        self.call()
        self.assertEqual(self.state()[0:2], (((0, 1),), ((0,),)))

    def test_missing_character_rejected(self):
        with self.assertRaisesRegex(pymysql.MySQLError, "Character does not exist"):
            self.call(guid=900003)
        self.assertEqual(self.state(900003), (((0, 0),), (), (), ()))
        self.call()
        self.assertEqual(self.state()[0], ((0, 1),))

    def test_unsupported_reward_rejected(self):
        self.execute("UPDATE mod_archipelago_item SET item_entry=119 WHERE guid=900001")
        with self.assertRaisesRegex(pymysql.MySQLError, "Unsupported reward item"):
            self.call()
        self.assert_pending()
        self.execute("UPDATE mod_archipelago_item SET item_entry=118 WHERE guid=900001")
        self.call()
        self.assertEqual(self.state()[0], ((0, 1),))

    def test_invalid_backpack_positions(self):
        for bag_slot, slot in ((19, 23), (255, 22), (255, 39)):
            with self.subTest(bag_slot=bag_slot, slot=slot):
                with self.assertRaisesRegex(pymysql.MySQLError, "Invalid backpack position"):
                    self.call(bag_slot=bag_slot, slot=slot)
                self.assert_pending()
        self.call(slot=38)
        self.assertEqual(self.state()[2], ((0, 38, 910001),))

    def test_bag_requires_persisted_equipped_parent_owned_by_character(self):
        with self.assertRaisesRegex(pymysql.MySQLError, "Equipped bag does not exist"):
            self.call(bag=910003, bag_slot=19, slot=0)
        self.assert_pending()
        self.equip_bag(owner=900002)
        before = self.state()
        with self.assertRaisesRegex(pymysql.MySQLError, "Equipped bag does not exist"):
            self.call(bag=910003, bag_slot=19, slot=0)
        self.assertEqual(self.state(), before)
        self.execute("UPDATE item_instance SET owner_guid=900001 WHERE guid=910003")
        for bag_slot in (18, 20, 23):
            with self.assertRaises(pymysql.MySQLError):
                self.call(bag=910003, bag_slot=bag_slot, slot=0)
        self.call(bag=910003, bag_slot=19, slot=0)
        self.assertEqual(self.state(), (
            ((0, 1),), ((0,),), ((910003, 0, 910001), (0, 19, 910003)),
            ((910001, 118, 1), (910003, 0, 1)),
        ))

    def test_failed_item_insert_rolls_back_receipt_and_flag(self):
        self.insert_item(item=910001, owner=900002)
        with self.assertRaises(pymysql.IntegrityError):
            self.call()
        self.assert_pending()
        self.assertEqual(self.execute("SELECT owner_guid FROM item_instance WHERE guid=910001"), ((900002,),))
        self.call(item=910002)
        self.assertEqual(self.state(), (
            ((0, 1),), ((0,),), ((0, 23, 910002),), ((910002, 118, 1),),
        ))

    def test_failed_inventory_insert_also_rolls_back_new_item(self):
        self.execute("""
            CREATE TRIGGER inventory_test_fail BEFORE INSERT ON character_inventory
            FOR EACH ROW BEGIN
                IF NEW.guid = 900001 THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Test inventory insert failure';
                END IF;
            END
        """)
        self.addCleanup(self.execute, "DROP TRIGGER IF EXISTS inventory_test_fail")
        with self.assertRaisesRegex(pymysql.MySQLError, "Test inventory insert failure"):
            self.call()
        self.assert_pending()
        self.execute("DROP TRIGGER inventory_test_fail")
        self.call()
        self.assertEqual(self.state(), (
            ((0, 1),), ((0,),), ((0, 23, 910001),), ((910001, 118, 1),),
        ))

    def test_concurrent_calls_grant_only_one_candidate(self):
        barrier = threading.Barrier(2)
        errors = []

        def deliver(item):
            try:
                with self.connect() as worker:
                    barrier.wait(timeout=5)
                    self.call(db=worker, item=item)
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=deliver, args=(item,), daemon=True)
                   for item in (910001, 910002)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertIn(self.state(), (
            (((0, 1),), ((0,),), ((0, 23, 910001),), ((910001, 118, 1),)),
            (((0, 1),), ((0,),), ((0, 23, 910002),), ((910002, 118, 1),)),
        ))

    def test_duplicate_receipt_is_an_error_not_an_extra_grant(self):
        self.execute("INSERT INTO mod_archipelago_delivery VALUES (900001, 0)")
        with self.assertRaises(pymysql.IntegrityError):
            self.call()
        self.assertEqual(self.state(), (((0, 0),), ((0,),), (), ()))
        self.execute("DELETE FROM mod_archipelago_delivery WHERE guid=900001")
        self.call()
        self.assertEqual(self.state()[0], ((0, 1),))

    def test_disconnect_before_commit_rolls_back_and_retry_delivers_once(self):
        # Only this isolated database and fixture character can enter the sleep.
        self.execute("""
            CREATE TRIGGER inventory_test_pause BEFORE INSERT ON character_inventory
            FOR EACH ROW BEGIN
                IF NEW.guid = 900001 THEN DO SLEEP(30); END IF;
            END
        """)
        self.addCleanup(self.execute, "DROP TRIGGER IF EXISTS inventory_test_pause")
        worker = self.connect()
        connection_id = worker.thread_id()
        errors = []

        def deliver():
            try:
                self.call(db=worker)
            except pymysql.MySQLError as error:
                errors.append(error)
            finally:
                worker.close()

        thread = threading.Thread(target=deliver, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                rows = self.execute("SELECT STATE FROM information_schema.PROCESSLIST WHERE ID=%s", (connection_id,))
                if rows == (("User sleep",),):
                    break
                time.sleep(0.02)
            else:
                self.fail("CALL did not reach the pre-commit inventory insert")
        finally:
            self.execute(f"KILL CONNECTION {connection_id}")
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.execute("DROP TRIGGER inventory_test_pause")
        self.assert_pending()
        self.call(item=910002)
        self.call(item=910001)
        self.assertEqual(self.state(), (
            ((0, 1),), ((0,),), ((0, 23, 910002),), ((910002, 118, 1),),
        ))


if __name__ == "__main__":
    unittest.main()
