"""Real MySQL tests. Only per-process wowpilago_v2_test_* fixtures are writable."""
import os
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

import pymysql

ROOT = Path(__file__).resolve().parents[1]
DATABASE = f"wowpilago_v2_test_{os.getpid()}"


@unittest.skipUnless(os.environ.get('WOWPILAGO_DB_PASSWORD') and os.environ.get('WOWPILAGO_TEST_DB_PORT'),
                     'Set WOWPILAGO_DB_PASSWORD and an explicit isolated WOWPILAGO_TEST_DB_PORT')
class V2EffectsSqlTests(unittest.TestCase):
    @classmethod
    def connect(cls, database=DATABASE):
        return pymysql.connect(host='127.0.0.1', port=int(os.environ['WOWPILAGO_TEST_DB_PORT']), user='root',
                               password=os.environ['WOWPILAGO_DB_PASSWORD'],
                               database=database, autocommit=True)

    @classmethod
    def setUpClass(cls):
        with cls.connect(None) as db, db.cursor() as c:
            c.execute(f'CREATE DATABASE IF NOT EXISTS `{DATABASE}`')
        cls.db = cls.connect()
        cls.addClassCleanup(cls.db.close)
        with cls.db.cursor() as c:
            c.execute('SET FOREIGN_KEY_CHECKS=0')
            c.execute('SHOW TABLES')
            for (table,) in c.fetchall():
                c.execute(f'DROP TABLE `{table}`')
            c.execute('SET FOREIGN_KEY_CHECKS=1')
            c.execute('''CREATE TABLE characters (
                guid INT UNSIGNED PRIMARY KEY, level TINYINT UNSIGNED NOT NULL DEFAULT 1,
                xp INT UNSIGNED NOT NULL DEFAULT 0, class TINYINT UNSIGNED NOT NULL DEFAULT 1,
                race TINYINT UNSIGNED NOT NULL DEFAULT 1, account INT UNSIGNED NOT NULL DEFAULT 1,
                name VARCHAR(12) NOT NULL DEFAULT 'Test', money INT UNSIGNED NOT NULL DEFAULT 0,
                online TINYINT UNSIGNED NOT NULL DEFAULT 0) ENGINE=InnoDB''')
            # Match the pinned core's complete item/inventory tables.
            c.execute('''CREATE TABLE item_instance (
                guid INT UNSIGNED NOT NULL DEFAULT 0 PRIMARY KEY,
                itemEntry INT UNSIGNED DEFAULT 0, owner_guid INT UNSIGNED NOT NULL DEFAULT 0,
                creatorGuid INT UNSIGNED NOT NULL DEFAULT 0, giftCreatorGuid INT UNSIGNED NOT NULL DEFAULT 0,
                count INT UNSIGNED NOT NULL DEFAULT 1, duration INT NOT NULL DEFAULT 0,
                charges TINYTEXT, flags INT UNSIGNED DEFAULT 0, enchantments TEXT NOT NULL,
                randomPropertyId SMALLINT NOT NULL DEFAULT 0,
                durability SMALLINT UNSIGNED NOT NULL DEFAULT 0,
                playedTime INT UNSIGNED NOT NULL DEFAULT 0, text TEXT,
                KEY idx_owner_guid(owner_guid)) ENGINE=InnoDB''')
            c.execute('''CREATE TABLE character_inventory (
                guid INT UNSIGNED NOT NULL DEFAULT 0, bag INT UNSIGNED NOT NULL DEFAULT 0,
                slot TINYINT UNSIGNED NOT NULL DEFAULT 0,
                item INT UNSIGNED NOT NULL DEFAULT 0 PRIMARY KEY,
                UNIQUE KEY guid(guid,bag,slot), KEY idx_guid(guid)) ENGINE=InnoDB''')
            for statement in (ROOT / 'sql/v2.sql').read_text().split(';'):
                if statement.strip():
                    c.execute(statement)
            before, routines = (ROOT / 'sql/v2_effects.sql').read_text().split('DELIMITER $$\n')
            for statement in before.split(';'):
                if statement.strip():
                    c.execute(statement)
            for routine in routines.split('DELIMITER ;')[0].split('$$'):
                if routine.strip():
                    c.execute(routine)

    def sql(self, statement, args=()):
        with self.db.cursor() as c:
            c.execute(statement, args)
            return c.fetchall()

    def setUp(self):
        self.sql('SET FOREIGN_KEY_CHECKS=0')
        for (table,) in self.sql('SHOW TABLES'):
            self.sql(f'DELETE FROM `{table}`')
        self.sql('SET FOREIGN_KEY_CHECKS=1')
        self.sql('INSERT INTO characters(guid) VALUES (1),(2)')
        for binding in (1, 2):
            self.sql('''INSERT INTO mod_archipelago_binding
                (id,character_guid,character_name,character_account,seed_name,team,slot,
                 class_id,race_id,faction,manifest_hash,manifest)
                VALUES (%s,%s,'Test',1,'effects-test',0,%s,1,1,'alliance',%s,'{}')''',
                     (binding, binding, binding, 'a' * 64))
            self.sql('INSERT INTO mod_archipelago_progress(binding_id) VALUES (%s)', (binding,))
            self.sql('INSERT INTO mod_archipelago_stock(binding_id,stock_index,item_entry,price) VALUES (%s,0,19019,3)', (binding,))
        self.index = 0

    def queue(self, kind, value, binding=1):
        self.index += 1
        index = self.index
        self.sql('INSERT INTO mod_archipelago_allowed_reward VALUES (%s,%s)', (binding, index))
        self.sql('''INSERT INTO mod_archipelago_reward
            (binding_id,item_index,ap_item,location_id,sender,flags,kind,value)
            VALUES (%s,%s,%s,-1,0,0,%s,%s)''', (binding, index, index, kind, value))
        return index

    def call(self, proc, args, db=None):
        with (db or self.db).cursor() as c:
            c.execute('CALL mod_archipelago_v2_' + proc + '(' + ','.join(['%s'] * len(args)) + ')', args)
            self.assertIsNone(c.description)
            while c.nextset():
                self.assertIsNone(c.description)

    def item_args(self, item=100, slot=23, bag=0, bag_slot=255):
        return [item, bag, bag_slot, slot, 123, 456, -7, '-1 0 0 0 0 ',
                0x1108, '1 2 3 ' * 12, -9, 10, 11, "Item's text"]

    def apply(self, index, entry=0, count=0, level=1, money=0, next_xp=1000, **kw):
        item = self.item_args(**kw) if entry else [0] * 7 + ['', 0, '', 0, 0, 0, '']
        self.call('apply_reward', [1, index, level, money, next_xp, entry, count] + item)

    def buy(self, binding=1, db=None, **kw):
        self.call('purchase', [binding, 0] + self.item_args(**kw), db=db)

    def progress(self):
        return self.sql('SELECT cap_items,banked_xp,access_flags,riding_flags,talent_unlocks,vouchers,last_level,victory FROM mod_archipelago_progress WHERE binding_id=1')[0]

    def pending(self, index):
        return self.sql('SELECT applied,applied_value,item_guid FROM mod_archipelago_reward WHERE binding_id=1 AND item_index=%s', (index,))[0]

    def test_exact_public_signatures(self):
        shared = [('p_item_guid','int unsigned'), ('p_bag_guid','int unsigned'),
                  ('p_bag_slot','tinyint unsigned'), ('p_slot','tinyint unsigned'),
                  ('p_creator','int unsigned'), ('p_gift','int unsigned'),
                  ('p_duration','int'), ('p_charges','varchar(64)'),
                  ('p_flags','int unsigned'), ('p_enchantments','text'),
                  ('p_random','smallint'), ('p_durability','smallint unsigned'),
                  ('p_played','int unsigned'), ('p_text','text')]
        prefixes = {
            'apply_reward': [('p_binding','bigint unsigned'), ('p_index','int unsigned'),
                             ('p_level','tinyint unsigned'), ('p_money','int unsigned'),
                             ('p_next_xp','int unsigned'), ('p_item_entry','int unsigned'),
                             ('p_count','int unsigned')],
            'purchase': [('p_binding','bigint unsigned'), ('p_stock_index','smallint unsigned')],
        }
        for proc, prefix in prefixes.items():
            self.assertEqual(self.sql('''SELECT PARAMETER_NAME,DTD_IDENTIFIER,PARAMETER_MODE
                FROM information_schema.PARAMETERS WHERE SPECIFIC_SCHEMA=DATABASE()
                AND SPECIFIC_NAME=%s ORDER BY ORDINAL_POSITION''',
                ('mod_archipelago_v2_' + proc,)),
                tuple((name, dtype, 'IN') for name, dtype in prefix + shared))

    def test_all_state_rewards_and_early_flags(self):
        for kind, value in [('outland', 1), ('northrend', 2)] + [('riding', n) for n in range(5)] + [('ability', 100), ('ability', 100)]:
            i = self.queue(kind, value)
            self.apply(i)
            self.apply(i)
        self.assertEqual(self.progress(), (0, 0, 3, 31, 0, 0, 1, 0))
        self.assertEqual(self.sql('SELECT * FROM mod_archipelago_ability'), ((1, 100),))
        # SQL records permission only. There is no character_spell or talent grant.
        for _ in range(14):
            self.apply(self.queue('talent', 1))
        self.assertEqual(self.progress()[4], 12)
        for _ in range(9):
            self.apply(self.queue('level_cap', 10))
        self.assertEqual(self.progress()[0], 7)
        self.assertEqual(self.pending(self.index)[:2], (1, 0))
        self.assertEqual(self.sql('SELECT level,xp FROM characters WHERE guid=1'), ((1, 0),))
        self.assertEqual(self.progress()[-1], 0)

    def test_204_vouchers_88_rewards(self):
        for value, count in ((1, 45), (3, 28), (5, 15)):
            for _ in range(count):
                i = self.queue('vouchers', value)
                self.apply(i)
                self.apply(i)
        self.assertEqual(self.progress()[5], 204)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM mod_archipelago_reward WHERE applied=1'), ((88,),))

    def test_cap_release_and_no_unrelated_bank_clear(self):
        self.sql('UPDATE characters SET level=10,xp=0 WHERE guid=1')
        self.sql('UPDATE mod_archipelago_progress SET banked_xp=800 WHERE binding_id=1')
        self.apply(self.queue('vouchers', 1), level=10)
        self.assertEqual(self.progress()[1], 800)
        i = self.queue('level_cap', 10)
        self.apply(i, level=10)
        self.apply(i, level=10)
        self.assertEqual(self.progress()[:2], (1, 0))
        self.assertEqual(self.sql('SELECT level,xp FROM characters WHERE guid=1'), ((10, 500),))
        self.assertEqual(self.progress()[-1], 0)

    def test_gold_and_potion_scaling(self):
        self.sql('UPDATE mod_archipelago_progress SET cap_items=7 WHERE binding_id=1')
        for level, money, entry in [(1,1000,118),(3,1000,858),(10,10000,858),
                (12,10000,929),(20,50000,929),(21,50000,1710),(35,50000,3928),
                (40,200000,3928),(45,200000,13446),(60,500000,13446),(70,1000000,33447),(80,1000000,33447)]:
            with self.subTest(level=level):
                self.sql('UPDATE characters SET level=%s,money=0 WHERE guid=1', (level,))
                i = self.queue('gold', 1)
                self.apply(i, level=level)
                self.assertEqual(self.pending(i)[1], money)
                i = self.queue('consumable', 1)
                self.apply(i, level=level, entry=entry, count=5, item=100+i, slot=23+level%16)
                self.assertEqual(self.pending(i)[0], 1)
                self.sql('DELETE FROM character_inventory')
        self.sql('UPDATE characters SET money=2147483647 WHERE guid=1')
        i = self.queue('gold', 1)
        self.apply(i, level=80, money=2147483647)
        self.assertEqual(self.pending(i), (0, 0, None))

    def test_physical_rewards_and_authorization_owner(self):
        i = self.queue('bag', 21841)
        self.apply(i, entry=21841, count=1)
        j = self.queue('legendary', 19019)
        self.apply(j, entry=19019, count=1, item=101, slot=24)
        self.apply(j, entry=19019, count=1, item=102, slot=25)
        self.assertEqual(self.sql('SELECT * FROM mod_archipelago_authorized_item ORDER BY item_guid'),
                         ((100, 1, 21841), (101, 1, 19019)))
        self.assertEqual(self.sql('SELECT flags FROM item_instance WHERE guid=100'), ((9,),))
        self.assertEqual(self.sql('SELECT owner_guid,flags,count FROM item_instance WHERE guid=101'), ((1, 9, 1),))
        self.assertEqual(self.sql('SELECT guid FROM item_instance WHERE guid=102'), ())
        self.assertEqual(self.pending(j), (1, 1, 101))

    def test_validation_and_rollback(self):
        i = self.queue('vouchers', 1)
        for update, undo in [
            ('UPDATE characters SET class=2 WHERE guid=1','UPDATE characters SET class=1 WHERE guid=1'),
            ('UPDATE characters SET race=2 WHERE guid=1','UPDATE characters SET race=1 WHERE guid=1'),
            ('UPDATE characters SET level=2 WHERE guid=1','UPDATE characters SET level=1 WHERE guid=1'),
            ("UPDATE mod_archipelago_binding SET status='archived' WHERE id=1", "UPDATE mod_archipelago_binding SET status='disconnected' WHERE id=1"),
            ('DELETE FROM mod_archipelago_allowed_reward WHERE binding_id=1', 'INSERT INTO mod_archipelago_allowed_reward VALUES (1,1)')]:
            self.sql(update)
            with self.assertRaises(pymysql.MySQLError):
                self.apply(i)
            self.assertEqual(self.pending(i), (0, 0, None))
            self.sql(undo)
        for kind, value in [('level_cap', 1), ('outland', 2), ('northrend', 1), ('riding', 5), ('talent', 2), ('vouchers', 2), ('gold', 2), ('consumable', 2), ('bag', 1), ('ability', 0)]:
            with self.assertRaises(pymysql.MySQLError):
                self.apply(self.queue(kind, value))
        with self.assertRaises(pymysql.MySQLError):
            self.apply(self.queue('bag', 21841), entry=118, count=1)
        self.assertEqual(self.progress()[5], 0)

    def test_purchase_balance_full_bags_replay_and_separate_slots(self):
        self.buy()
        self.assertEqual(self.sql('SELECT sold FROM mod_archipelago_stock'), ((0,), (0,)))
        self.sql('UPDATE mod_archipelago_progress SET vouchers=5')
        i = self.queue('bag', 21841)
        self.apply(i, entry=21841, count=1)
        self.buy(item=101)
        self.assertEqual(self.progress()[5], 5)
        self.assertEqual(self.sql('SELECT * FROM mod_archipelago_purchase'), ())
        self.buy(item=101, slot=24)
        self.buy(item=102, slot=25)
        self.buy(binding=2, item=103)
        self.assertEqual(self.progress()[5], 2)
        self.assertEqual(self.sql('SELECT binding_id,item_guid,price FROM mod_archipelago_purchase ORDER BY binding_id'), ((1,101,3),(2,103,3)))
        self.assertEqual(self.sql('SELECT binding_id,item_entry FROM mod_archipelago_authorized_item ORDER BY binding_id,item_guid'),
                         ((1,21841),(1,19019),(2,19019)))

    def test_bag_parent_owned_and_equipped(self):
        self.sql('UPDATE mod_archipelago_progress SET vouchers=5')
        with self.assertRaises(pymysql.MySQLError):
            self.buy(bag=500, bag_slot=19, slot=0)
        self.sql("INSERT INTO item_instance(guid,owner_guid,itemEntry,enchantments) VALUES (500,2,21841,'')")
        self.sql('INSERT INTO character_inventory VALUES (1,0,19,500)')
        with self.assertRaises(pymysql.MySQLError):
            self.buy(bag=500, bag_slot=19, slot=0)
        self.sql('UPDATE item_instance SET owner_guid=1 WHERE guid=500')
        self.buy(bag=500, bag_slot=19, slot=0)
        self.assertEqual(self.sql('SELECT bag,slot FROM character_inventory WHERE item=100'), ((500,0),))

    def test_faults_at_every_insert_point(self):
        self.sql('UPDATE mod_archipelago_progress SET vouchers=5')
        for table in ('item_instance','character_inventory','mod_archipelago_purchase','mod_archipelago_authorized_item'):
            with self.subTest(table=table):
                self.sql(f"CREATE TRIGGER effects_fail BEFORE INSERT ON {table} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='injected failure'")
                try:
                    with self.assertRaisesRegex(pymysql.MySQLError, 'injected failure'):
                        self.buy()
                finally:
                    self.sql('DROP TRIGGER effects_fail')
                self.assertEqual(self.progress()[5], 5)
                self.assertEqual(self.sql('SELECT * FROM item_instance'), ())
                self.assertEqual(self.sql('SELECT * FROM character_inventory'), ())
                self.assertEqual(self.sql('SELECT * FROM mod_archipelago_purchase'), ())
                self.assertEqual(self.sql('SELECT sold FROM mod_archipelago_stock WHERE binding_id=1'), ((0,),))
        # Reward receipt update must also roll back item and authorization.
        i = self.queue('legendary', 19019)
        self.sql("CREATE TRIGGER effects_fail BEFORE UPDATE ON mod_archipelago_reward FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='injected failure'")
        try:
            with self.assertRaises(pymysql.MySQLError):
                self.apply(i, entry=19019, count=1)
        finally:
            self.sql('DROP TRIGGER effects_fail')
        self.assertEqual(self.pending(i), (0,0,None))
        self.assertEqual(self.sql('SELECT * FROM item_instance'), ())
        self.assertEqual(self.sql('SELECT * FROM mod_archipelago_authorized_item'), ())

    def test_concurrent_purchase(self):
        self.sql('UPDATE mod_archipelago_progress SET vouchers=5')
        barrier = threading.Barrier(2)
        errors = []
        def run(item):
            try:
                with self.connect() as db:
                    barrier.wait(timeout=5)
                    self.buy(db=db, item=item)
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=run, args=(i,)) for i in (100,101)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.progress()[5], 2)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM item_instance'), ((1,),))

    def test_connection_loss_during_call_and_replay(self):
        self.sql('UPDATE mod_archipelago_progress SET vouchers=5')
        self.sql('CREATE TRIGGER effects_pause BEFORE INSERT ON character_inventory FOR EACH ROW DO SLEEP(30)')
        worker = self.connect()
        errors = []
        def run():
            try:
                self.buy(db=worker)
            except pymysql.MySQLError as error:
                errors.append(error)
            finally:
                worker.close()
        thread = threading.Thread(target=run)
        thread.start()
        try:
            deadline = time.monotonic()+10
            while time.monotonic()<deadline:
                if self.sql('SELECT STATE FROM information_schema.PROCESSLIST WHERE ID=%s', (worker.thread_id(),)) == (('User sleep',),):
                    break
                time.sleep(.02)
            else:
                self.fail('CALL never reached insertion')
        finally:
            self.sql('KILL CONNECTION %s', (worker.thread_id(),))
            thread.join(5)
            self.sql('DROP TRIGGER effects_pause')
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.progress()[5], 5)
        self.assertEqual(self.sql('SELECT * FROM item_instance'), ())
        self.buy(item=101)
        self.buy(item=100)
        self.assertEqual(self.sql('SELECT item_guid FROM mod_archipelago_purchase'), ((101,),))

    def test_level_bank_and_empty_parameter_boundaries(self):
        i = self.queue('vouchers', 1)
        for level in (0, 11, 81):
            self.sql('UPDATE characters SET level=%s WHERE guid=1', (level,))
            with self.assertRaises(pymysql.MySQLError):
                self.apply(i, level=level)
        self.sql('UPDATE characters SET level=1 WHERE guid=1')
        self.sql('UPDATE mod_archipelago_progress SET last_level=2 WHERE binding_id=1')
        with self.assertRaises(pymysql.MySQLError):
            self.apply(i)
        self.sql('UPDATE mod_archipelago_progress SET last_level=1,banked_xp=1 WHERE binding_id=1')
        with self.assertRaises(pymysql.MySQLError):
            self.apply(i)
        self.sql('UPDATE mod_archipelago_progress SET banked_xp=0 WHERE binding_id=1')
        args = [1,i,1,0,1000,0,0] + self.item_args()
        with self.assertRaises(pymysql.MySQLError):
            self.call('apply_reward', args)
        self.assertEqual(self.progress()[5], 0)
        self.sql('UPDATE characters SET xp=17 WHERE guid=1')
        self.apply(self.queue('level_cap', 10))
        self.assertEqual(self.sql('SELECT level,xp FROM characters WHERE guid=1'), ((1,17),))

    def test_reward_full_slot_and_duplicate_guid_stay_pending(self):
        i = self.queue('bag', 21841)
        self.apply(i, entry=21841, count=1)
        j = self.queue('consumable', 1)
        self.apply(j, entry=118, count=5, item=101)
        self.assertEqual(self.pending(j), (0,0,None))
        with self.assertRaises(pymysql.IntegrityError):
            self.apply(j, entry=118, count=5, slot=24)
        self.assertEqual(self.pending(j), (0,0,None))
        self.apply(j, entry=118, count=5, item=101, slot=24)
        self.assertEqual(self.pending(j), (1,5,101))
        self.assertEqual(self.sql('SELECT count FROM item_instance WHERE guid=101'), ((5,),))

    def test_character_delete_preserves_history(self):
        i = self.queue('legendary', 19019)
        self.apply(i, entry=19019, count=1)
        self.sql('''INSERT INTO mod_archipelago_binding
            (id,character_guid,character_name,character_account,seed_name,team,slot,
             class_id,race_id,faction,manifest_hash,manifest)
            VALUES (3,NULL,'Detached',1,'unrelated',0,3,1,1,'alliance',%s,'{}')''', ('c' * 64,))
        other = self.sql('SELECT * FROM mod_archipelago_binding WHERE id<>1 ORDER BY id')
        self.sql('DELETE FROM characters WHERE guid=1')
        self.assertEqual(self.sql('SELECT character_guid,status FROM mod_archipelago_binding WHERE id=1'),
                         ((None, 'archived'),))
        self.assertEqual(self.sql('SELECT * FROM mod_archipelago_binding WHERE id<>1 ORDER BY id'), other)
        self.assertEqual(self.pending(i), (1,1,100))
        self.apply(i, entry=19019, count=1, item=101)
        with self.assertRaises(pymysql.MySQLError):
            self.apply(self.queue('vouchers', 1))
        self.sql('DELETE FROM item_instance WHERE guid=100')
        self.assertEqual(self.sql('SELECT * FROM mod_archipelago_authorized_item'), ())
        self.assertEqual(self.pending(i), (1,1,100))

    def test_character_delete_archive_rolls_back_with_histories(self):
        self.queue('vouchers', 1)
        tables = ['characters'] + [t for (t,) in self.sql('SHOW TABLES')
                                   if t.startswith('mod_archipelago_')]
        before = {t: sorted(self.sql(f'SELECT * FROM `{t}`'), key=repr) for t in tables}
        self.db.begin()
        try:
            self.sql('DELETE FROM characters WHERE guid=1')
            self.assertEqual(self.sql('SELECT character_guid,status FROM mod_archipelago_binding WHERE id=1'),
                             ((None, 'archived'),))
            with self.assertRaises(pymysql.IntegrityError):
                self.sql('INSERT INTO characters(guid) VALUES (2)')
        finally:
            self.db.rollback()
        self.assertEqual({t: sorted(self.sql(f'SELECT * FROM `{t}`'), key=repr) for t in tables}, before)

    def test_character_delete_trigger_install_is_idempotent(self):
        for statement in (ROOT / 'sql/v2.sql').read_text().split(';'):
            if statement.strip():
                self.sql(statement)
        self.assertEqual(self.sql('''SELECT TRIGGER_NAME,ACTION_TIMING,EVENT_MANIPULATION,
            EVENT_OBJECT_TABLE FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE()'''),
            (('mod_archipelago_archive_character', 'BEFORE', 'DELETE', 'characters'),))
        self.sql('DELETE FROM characters WHERE guid=1')
        self.assertEqual(self.sql('SELECT character_guid,status FROM mod_archipelago_binding WHERE id=1'),
                         ((None, 'archived'),))

    def test_character_delete_sees_binding_created_after_lookup_miss(self):
        self.sql('INSERT INTO characters(guid) VALUES (3)')
        self.assertEqual(self.sql('SELECT id FROM mod_archipelago_binding WHERE character_guid=3'), ())
        self.sql('''INSERT INTO mod_archipelago_binding
            (id,character_guid,character_name,character_account,seed_name,team,slot,
             class_id,race_id,faction,manifest_hash,manifest)
            VALUES (3,3,'Test',1,'late-bind',0,3,1,1,'alliance',%s,'{}')''', ('b' * 64,))
        # Execute only the core DELETE. No successful prelookup or hook UPDATE is needed.
        self.sql('DELETE FROM characters WHERE guid=3')
        self.assertEqual(self.sql('SELECT character_guid,status FROM mod_archipelago_binding WHERE id=3'),
                         ((None, 'archived'),))
        self.sql('INSERT INTO characters(guid) VALUES (3)')
        self.assertEqual(self.sql('SELECT id FROM mod_archipelago_binding WHERE character_guid=3'), ())


class SqlIsolationConfigurationTests(unittest.TestCase):
    def test_explicit_fixture_port_is_used_without_connecting(self):
        with patch.dict(os.environ, {'WOWPILAGO_DB_PASSWORD': 'fixture', 'WOWPILAGO_TEST_DB_PORT': '13318'}, clear=True), \
                patch.object(pymysql, 'connect') as connect:
            V2EffectsSqlTests.connect()
            self.assertEqual(connect.call_args.kwargs['port'], 13318)
            self.assertEqual(connect.call_args.kwargs['database'], DATABASE)

    def test_missing_port_cannot_fall_back_to_the_realm(self):
        with patch.dict(os.environ, {'WOWPILAGO_DB_PASSWORD': 'fixture'}, clear=True), \
                patch.object(pymysql, 'connect') as connect:
            with self.assertRaises(KeyError):
                V2EffectsSqlTests.connect()
            connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
