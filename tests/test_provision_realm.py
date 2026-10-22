"""Offline checks plus opt-in MySQL checks in a PID-only disposable schema."""
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import provision_realm as p


TRIGGER_NAME = 'mod_archipelago_archive_character'
TRIGGER_SQL = (f'CREATE TRIGGER IF NOT EXISTS {TRIGGER_NAME} BEFORE DELETE ON characters '
               "FOR EACH ROW UPDATE mod_archipelago_binding SET status='archived',character_guid=NULL "
               'WHERE character_guid=OLD.guid')


class ProvisionTests(unittest.TestCase):
    def test_wrath_srp_vector_and_normalization(self):
        self.assertEqual(p.verifier('test', 'test', bytes(range(32))).hex(),
                         'a57079472ffeddf921a6477b3b340f3691625bb0f1313427f38742e6f128b614')
        self.assertEqual(p.verifier('APV2A', 'test-only', bytes(32)),
                         p.verifier('apv2a', 'TEST-ONLY', bytes(32)))
        for password in ('', 'x' * 17, 'é'):
            with self.assertRaises(ValueError):
                p.verifier('APV2A', password, bytes(32))

    def test_collision_never_resets_account(self):
        row = dict(email=p.MARKER, reg_mail=p.MARKER, salt=bytes(32),
                   verifier=p.verifier('APV2A', 'test-only', bytes(32)))
        p.check_account(row, 'APV2A', 'test-only')
        for bad in ({**row, 'email': 'someone@else'}, {**row, 'reg_mail': ''},
                    {**row, 'verifier': bytes(32)}):
            with self.assertRaises(ValueError):
                p.check_account(bad, 'APV2A', 'test-only')

    def test_sql_delimiters_and_no_destructive_character_ddl(self):
        schema = list(p.statements((p.ROOT / 'sql/v2.sql').read_text()))
        tables = [s for s in schema if s.startswith('CREATE TABLE IF NOT EXISTS mod_archipelago_')]
        triggers = [s for s in schema if s.startswith('CREATE TRIGGER IF NOT EXISTS ')]
        self.assertEqual(len(schema), 12)
        self.assertEqual(len(tables), 11)
        self.assertEqual(len(triggers), 1)
        self.assertEqual(re.sub(r'\s+', '', triggers[0]), re.sub(r'\s+', '', TRIGGER_SQL))
        effects = list(p.statements((p.ROOT / 'sql/v2_effects.sql').read_text()))
        self.assertEqual(len(effects), 6)
        self.assertEqual(sum(s.startswith('CREATE PROCEDURE') for s in effects), 3)
        with self.assertRaises(ValueError):
            list(p.statements('SELECT 1'))
        self.assertEqual(list(p.statements('INSERT INTO t VALUES\n(1),\n(2);')), ['INSERT INTO t VALUES\n(1),\n(2)'])

    def test_ddl_name_accepts_trigger_and_rejects_destructive_ddl(self):
        for sql in (TRIGGER_SQL, TRIGGER_SQL.replace(' IF NOT EXISTS', ''),
                    TRIGGER_SQL.replace(TRIGGER_NAME, f'`{TRIGGER_NAME}`')):
            self.assertEqual(p.ddl_name(sql), TRIGGER_NAME)
        for sql in (f'DROP TRIGGER IF EXISTS {TRIGGER_NAME}',
                    'DROP TABLE mod_archipelago_binding', 'DELETE FROM mod_archipelago_binding',
                    'ALTER TABLE mod_archipelago_binding DROP COLUMN character_guid'):
            with self.subTest(sql=sql), self.assertRaisesRegex(ValueError, 'Unexpected fixture DDL'):
                p.ddl_name(sql)

    def test_character_plan_uses_object_specific_identity_filters(self):
        sources = {'v2.sql': 'CREATE TABLE IF NOT EXISTS mod_archipelago_binding (id INT);\n'
                   + TRIGGER_SQL + ';\n',
                   'v2_effects.sql': 'DROP PROCEDURE IF EXISTS mod_archipelago_v2_fixture;\n'
                   'CREATE PROCEDURE mod_archipelago_v2_fixture() SELECT 1;\n'}
        with patch.object(p, 'query', return_value=[]) as query:
            plan, objects = p.character_plan(None, sources, {})
        self.assertEqual(plan, ['CREATE TABLE IF NOT EXISTS mod_archipelago_binding (id INT)',
                                TRIGGER_SQL, 'CREATE PROCEDURE mod_archipelago_v2_fixture() SELECT 1'])
        self.assertEqual(objects, {'mod_archipelago_binding': 'TABLE', TRIGGER_NAME: 'TRIGGER',
                                   'mod_archipelago_v2_fixture': 'PROCEDURE'})
        self.assertEqual([call.args for call in query.call_args_list], [
            (None, 'SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s',
             ('acore_characters', 'mod_archipelago_binding')),
            (None, 'SELECT 1 FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s AND TRIGGER_NAME=%s',
             ('acore_characters', TRIGGER_NAME)),
            (None, 'SELECT 1 FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_NAME=%s',
             ('acore_characters', 'mod_archipelago_v2_fixture'))])

    def test_object_definitions_preserve_trigger_sql_not_metadata(self):
        for kind, name, row, expected in (
                ('TABLE', 'mod_archipelago_binding',
                 {'Create Table': 'CREATE TABLE mod_archipelago_binding (id INT) AUTO_INCREMENT=42 ENGINE=InnoDB'},
                 'CREATE TABLE mod_archipelago_binding (id INT) ENGINE=InnoDB'),
                ('PROCEDURE', 'mod_archipelago_v2_fixture',
                 {'Create Procedure': 'CREATE PROCEDURE mod_archipelago_v2_fixture() SELECT 1'},
                 'CREATE PROCEDURE mod_archipelago_v2_fixture() SELECT 1'),
                ('TRIGGER', TRIGGER_NAME,
                 {'Trigger': TRIGGER_NAME, 'sql_mode': 'STRICT_TRANS_TABLES',
                  'SQL Original Statement': TRIGGER_SQL, 'character_set_client': 'utf8mb4',
                  'collation_connection': 'utf8mb4_general_ci', 'Database Collation': 'utf8mb4_general_ci',
                  'Created': '2026-10-19 15:06:00'}, TRIGGER_SQL)):
            with self.subTest(kind=kind), patch.object(p, 'query', return_value=[row]) as query:
                definition = p.object_definition(None, 'acore_characters', kind, name)
                self.assertEqual(definition, expected)
                query.assert_called_once_with(None, f'SHOW CREATE {kind} `acore_characters`.`{name}`')
                receipt = json.loads(json.dumps({'objects': {name: definition}}))
                self.assertEqual(receipt['objects'][name], expected)

    def test_existing_trigger_requires_matching_receipt(self):
        sources = {'v2.sql': TRIGGER_SQL + ';\n', 'v2_effects.sql': ''}
        for objects in ({}, {TRIGGER_NAME: TRIGGER_SQL},
                        {TRIGGER_NAME: TRIGGER_SQL.replace("'archived'", "'disconnected'")}):
            receipt = json.loads(json.dumps({'objects': objects}))
            with self.subTest(objects=objects), patch.object(p, 'query', side_effect=[
                    [{'present': 1}], [{'SQL Original Statement': TRIGGER_SQL}]]):
                if objects.get(TRIGGER_NAME) == TRIGGER_SQL:
                    self.assertEqual(p.character_plan(None, sources, receipt), ([], {TRIGGER_NAME: 'TRIGGER'}))
                else:
                    with self.assertRaisesRegex(ValueError, f'Unverified existing {TRIGGER_NAME}'):
                        p.character_plan(None, sources, receipt)
            self.assertEqual(receipt, {'objects': objects})

    def test_character_plan_rejects_destructive_ddl(self):
        for sql in (f'DROP TRIGGER IF EXISTS {TRIGGER_NAME}',
                    'DROP TABLE mod_archipelago_binding', 'DELETE FROM mod_archipelago_binding'):
            with self.subTest(sql=sql), patch.object(p, 'query') as query:
                with self.assertRaisesRegex(ValueError, 'Unexpected fixture DDL'):
                    p.character_plan(None, {'v2.sql': sql + ';\n', 'v2_effects.sql': ''}, {})
                query.assert_not_called()

    def test_guard_rejects_wrong_uuid_or_external_binding(self):
        info = dict(Config=dict(Labels={'com.docker.compose.project': 'wow-test',
                                       'com.docker.compose.service': 'database'}),
                    NetworkSettings=dict(Ports={'3306/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '13317'}]}),
                    Mounts=[dict(Destination='/var/lib/mysql', Source=str(p.ROOT.parent / 'wow-test/data/mysql'))])
        with patch.object(p.subprocess, 'check_output', side_effect=lambda *a, **k: json.dumps([info]).encode()), \
                patch.object(p, 'query', return_value=[dict(uuid='not-our-database')]):
            with self.assertRaisesRegex(ValueError, 'UUID'):
                p.guard(None)
            info['NetworkSettings']['Ports']['3306/tcp'][0]['HostIp'] = '0.0.0.0'
            with self.assertRaisesRegex(ValueError, 'loopback'):
                p.guard(None)

    def test_playerbots_import_is_add_only(self):
        source = ''.join(f'DROP TABLE IF EXISTS `t{i}`;\nCREATE TABLE `t{i}` (id INT);\n'
                         f'DELETE FROM `t{i}`;\nINSERT INTO `t{i}` VALUES (1);\n' for i in range(29))
        plan = p.playerbots_plan({'fixture.sql': source})
        self.assertEqual(len(plan), 58)
        self.assertTrue(all(s.startswith(('CREATE TABLE', 'INSERT INTO')) for s in plan))
        with self.assertRaises(ValueError):
            p.playerbots_plan({'bad.sql': 'USE acore_characters;\n'})

    @unittest.skipUnless((p.PRIVATE / 'override.yaml').exists(), 'private local configs not prepared')
    def test_compose_private_config(self):
        private = p.PRIVATE
        text = (private / 'override.yaml').read_text()
        self.assertIn('!override', text)
        self.assertNotIn('7878:', text)
        self.assertNotIn('0.0.0.0:', text)
        world = (private / 'config/worldserver.conf').read_text()
        for key, value in {'MapUpdate.Threads': '1', 'MaxPlayerLevel': '80', 'Rate.Talent': '1',
                           'Warden.Enabled': '0', 'Updates.EnableDatabases': '0',
                           'Updates.AutoSetup': '0', 'SOAP.Enabled': '0', 'Ra.Enable': '0'}.items():
            self.assertRegex(world, rf'(?m)^{re.escape(key)}\s*=\s*{value}$')
        self.assertTrue(all(value == '1' for value in re.findall(r'(?m)^Rate.XP.\S+\s*=\s*(\S+)$', world)))
        bots = (private / 'config/modules/playerbots.conf').read_text()
        for key in ('Enabled', 'RandomBotAutologin', 'BotAutologin', 'MinRandomBots', 'MaxRandomBots',
                    'RandomBotAccountCount', 'AddClassAccountPoolSize', 'AutoDoQuests'):
            self.assertRegex(bots, rf'(?m)^AiPlayerbot.{key}\s*=\s*0$')
        self.assertIn('acore_playerbots_v2', bots)


@unittest.skipUnless(os.environ.get('WOWPILAGO_PROVISION_MYSQL_TEST') == '1', 'opt-in isolated MySQL checks')
class MysqlProvisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pymysql
        cls.db = pymysql.connect(host='127.0.0.1', port=13317, user='root',
                                 password=os.environ['WOWPILAGO_DB_PASSWORD'], autocommit=True,
                                 cursorclass=pymysql.cursors.DictCursor)
        p.guard(cls.db)
        cls.schema = f'wowpilago_provision_test_{os.getpid()}'
        # CREATE without IF NOT EXISTS refuses stale/colliding test schemas.
        p.execute(cls.db, f'CREATE DATABASE `{cls.schema}`')
        try:
            p.execute(cls.db, f'USE `{cls.schema}`')
            for table in ('account', 'account_access', 'realmcharacters', 'realmlist'):
                p.execute(cls.db, f'CREATE TABLE `{table}` LIKE acore_auth.`{table}`')
            p.execute(cls.db, 'INSERT INTO realmlist (id,name) VALUES (1,"PID fixture")')
            for table in ('characters', 'item_instance'):
                p.execute(cls.db, f'CREATE TABLE `{table}` LIKE acore_characters.`{table}`')
            for filename in ('v2.sql', 'v2_effects.sql'):
                for sql in p.statements((p.ROOT / 'sql' / filename).read_text()):
                    if not sql.startswith('DROP '):
                        p.execute(cls.db, sql)
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        p.execute(cls.db, f'DROP DATABASE `{cls.schema}`')
        cls.db.close()

    def test_raw_sql_percent_literals(self):
        p.execute(self.db, 'CREATE TABLE percent_fixture (value VARCHAR(20))')
        p.execute(self.db, "INSERT INTO percent_fixture VALUES ('100% literal')")
        self.assertEqual(p.query(self.db, "SELECT value FROM percent_fixture WHERE value LIKE '100%'")[0]['value'],
                         '100% literal')

    def test_add_only_idempotency_and_collision(self):
        names = (f'APVPID{os.getpid()}',)
        password = 'test-only'
        missing = p.accounts_plan(self.db, password, names, self.schema)
        self.assertEqual(missing, list(names))
        p.add_accounts(self.db, password, missing, self.schema)
        before = p.query(self.db, 'SELECT * FROM account')
        self.assertEqual(p.accounts_plan(self.db, password, names, self.schema), [])
        p.add_accounts(self.db, password, [], self.schema)
        self.assertEqual(before, p.query(self.db, 'SELECT * FROM account'))
        self.assertEqual(p.query(self.db, 'SELECT numchars FROM realmcharacters'), [dict(numchars=0)])
        self.assertFalse(p.query(self.db, 'SELECT * FROM account_access'))
        with self.assertRaises(ValueError):
            p.accounts_plan(self.db, 'wrong-password', names, self.schema)
        self.assertEqual(before, p.query(self.db, 'SELECT * FROM account'))

    def test_merchant_additive_and_collision(self):
        for table in ('creature_template', 'creature_template_model', 'creature'):
            p.execute(self.db, f'CREATE TABLE `{table}` LIKE acore_world.`{table}`')
        text = (p.ROOT / 'sql/world.sql').read_text()
        plan = p.world_plan(self.db, text)
        self.assertEqual(len(plan), 12)
        for sql in plan:
            p.execute(self.db, sql)
        self.assertEqual(p.world_plan(self.db, text), [])
        p.execute(self.db, "UPDATE creature_template SET name='PID collision' WHERE entry=900500")
        with self.assertRaisesRegex(ValueError, 'collision'):
            p.world_plan(self.db, text)


if __name__ == '__main__':
    unittest.main()
