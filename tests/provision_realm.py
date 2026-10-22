#!/usr/bin/env python3
"""Offline, ADD-only fixture preparation for this one private wow-test database."""
import argparse
import datetime as dt
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / '.local/v2-realm'
BUILD = ROOT / '.local/v2-build/20261019T150600.624050Z'
CONTAINER = 'wow-test-database-1'
UUID = '22e1df15-a702-11f1-b183-1afc4010fddc'
ACCOUNTS = tuple('APV2' + letter for letter in 'ABCDEF')
MARKER = 'wowpilago-fixture@invalid'
N = int('894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7', 16)
PB = 'acore_playerbots_v2'


def verifier(username, password, salt):
    if not password or not password.isascii() or len(password) > 16:
        raise ValueError('Required account password must be ASCII, 1..16 characters')
    if len(salt) != 32:
        raise ValueError('SRP6 salt must be 32 bytes')
    identity = hashlib.sha1(f'{username.upper()}:{password.upper()}'.encode('ascii')).digest()
    exponent = int.from_bytes(hashlib.sha1(salt + identity).digest(), 'little')
    return pow(7, exponent, N).to_bytes(32, 'little')


def check_account(row, username, password):
    if row and (row['email'] != MARKER or row['reg_mail'] != MARKER or
                not hmac.compare_digest(bytes(row['verifier']),
                                        verifier(username, password, bytes(row['salt'])))):
        raise ValueError(f'{username}: existing account is not our matching fixture; refusing')


def query(db, sql, args=None):
    with db.cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.fetchall()


def execute(db, sql, args=None):
    with db.cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.lastrowid


def guard(db):
    info = json.loads(subprocess.check_output(['docker', 'inspect', CONTAINER]))[0]
    labels = info['Config']['Labels']
    ports = info['NetworkSettings']['Ports']['3306/tcp']
    mounts = info['Mounts']
    if (labels.get('com.docker.compose.project') != 'wow-test' or
            labels.get('com.docker.compose.service') != 'database' or
            ports != [{'HostIp': '127.0.0.1', 'HostPort': '13317'}] or
            not any(m['Destination'] == '/var/lib/mysql' and
                    Path(m['Source']).resolve() == (ROOT.parent / 'wow-test/data/mysql').resolve()
                    for m in mounts)):
        raise ValueError('Not the known loopback wow-test database container/volume')
    if query(db, 'SELECT @@server_uuid AS uuid')[0]['uuid'] != UUID:
        raise ValueError('Database server UUID mismatch')
    running = subprocess.check_output(['docker', 'ps', '--filter', 'label=com.docker.compose.project=wow-test',
                                       '--format', '{{.Label "com.docker.compose.service"}}'], text=True)
    if set(running.splitlines()) - {'database'}:
        raise ValueError('Stop realm/import services before preparing fixtures')
    realm = query(db, 'SELECT * FROM acore_auth.realmlist')
    if (len(realm) != 1 or realm[0]['id'] != 1 or realm[0]['address'] != '127.0.0.1' or
            realm[0]['localAddress'] != '127.0.0.1' or realm[0]['port'] != 8085 or
            realm[0]['allowedSecurityLevel'] != 0 or realm[0]['gamebuild'] != 12340):
        raise ValueError('Unexpected realmlist; refusing to alter it')
    chars = query(db, 'SELECT guid,name FROM acore_characters.characters WHERE guid IN (1,2,3) ORDER BY guid')
    if chars != [dict(guid=1, name='Test'), dict(guid=2, name='Apbags'), dict(guid=3, name='Approbe')]:
        raise ValueError('Protected character identity mismatch')


def statements(text):
    """Read the repository's line-delimited SQL and DELIMITER procedure files."""
    # shortcut: fixture statements must end on a line boundary; revisit if SQL inputs change.
    delimiter, pending = ';', []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith(('--', '/*', '*')):
            continue
        if line.startswith('DELIMITER '):
            if pending:
                raise ValueError('SQL delimiter inside statement')
            delimiter = line.split()[1]
            continue
        pending.append(line)
        if line.rstrip().endswith(delimiter):
            yield '\n'.join(pending).rstrip()[:-len(delimiter)].strip()
            pending = []
    if pending:
        raise ValueError('Unterminated SQL statement')


def playerbots_plan(sources):
    plan = []
    names = set()
    for text in sources.values():
        for sql in statements(text):
            if re.fullmatch(r'(?:DROP TABLE IF EXISTS|DELETE FROM) `\w+`', sql):
                continue
            if not re.match(r'(?:CREATE TABLE(?: IF NOT EXISTS)?|INSERT INTO) `', sql):
                raise ValueError('Unexpected playerbots base statement: ' + sql[:100])
            if sql.startswith('CREATE TABLE'):
                names.add(ddl_name(sql))
            plan.append(sql)
    if len(names) != 29:
        raise ValueError('Unexpected playerbots base table count')
    return plan


def ddl_name(sql):
    match = re.match(r'CREATE (?:(?:TABLE|TRIGGER)(?: IF NOT EXISTS)?|PROCEDURE) `?(\w+)`?', sql)
    if not match:
        raise ValueError('Unexpected fixture DDL')
    return match[1]


def object_definition(db, database, kind, name):
    rows = query(db, f'SHOW CREATE {kind} `{database}`.`{name}`')
    definition = rows[0][{'TABLE': 'Create Table', 'PROCEDURE': 'Create Procedure',
                          'TRIGGER': 'SQL Original Statement'}[kind]]
    if kind == 'TABLE':
        definition = re.sub(r'AUTO_INCREMENT=\d+ ', '', definition)
    return definition


def character_plan(db, sources, receipt):
    plan, objects = [], {}
    for filename in ('v2.sql', 'v2_effects.sql'):
        for sql in statements(sources[filename]):
            if sql.startswith('DROP PROCEDURE IF EXISTS mod_archipelago_v2_'):
                continue
            name = ddl_name(sql)
            kind = sql.split()[1]
            catalog, prefix = {'TABLE': ('TABLES', 'TABLE'), 'PROCEDURE': ('ROUTINES', 'ROUTINE'),
                               'TRIGGER': ('TRIGGERS', 'TRIGGER')}[kind]
            exists = query(db, f'SELECT 1 FROM information_schema.{catalog} '
                           f'WHERE {prefix}_SCHEMA=%s AND {prefix}_NAME=%s', ('acore_characters', name))
            objects[name] = kind
            if exists:
                actual = object_definition(db, 'acore_characters', kind, name)
                if receipt.get('objects', {}).get(name) != actual:
                    raise ValueError(f'Unverified existing {name}; refusing to replace it')
            else:
                plan.append(sql)
    return plan, objects


def accounts_plan(db, password, names=ACCOUNTS, schema='acore_auth'):
    missing = []
    for name in names:
        rows = query(db, f'SELECT * FROM `{schema}`.account WHERE username=%s', (name,))
        check_account(rows[0] if rows else None, name, password)
        if not rows:
            missing.append(name)
            continue
        account = rows[0]
        if query(db, f'SELECT * FROM `{schema}`.account_access WHERE id=%s AND gmlevel<>0', (account['id'],)):
            raise ValueError(f'{name}: existing fixture has GM access')
        if account['expansion'] != 2:
            raise ValueError(f'{name}: existing fixture expansion mismatch')
        if not query(db, f'SELECT * FROM `{schema}`.realmcharacters WHERE acctid=%s AND realmid=1', (account['id'],)):
            raise ValueError(f'{name}: existing fixture lacks realmcharacters initialization')
    return missing


def add_accounts(db, password, names, schema='acore_auth'):
    # No account_access row means SEC_PLAYER / GM level 0. Never touch existing accounts.
    db.begin()
    try:
        for name in names:
            salt = secrets.token_bytes(32)
            account_id = execute(db, f'INSERT INTO `{schema}`.account '
                                 '(username,salt,verifier,expansion,email,reg_mail) VALUES (%s,%s,%s,2,%s,%s)',
                                 (name, salt, verifier(name, password, salt), MARKER, MARKER))
            execute(db, f'INSERT INTO `{schema}`.realmcharacters (realmid,acctid,numchars) '
                        f'SELECT id,%s,0 FROM `{schema}`.realmlist', (account_id,))
        db.commit()
    except Exception:
        db.rollback()
        raise


def world_plan(db, text):
    for condition in re.findall(r'IF EXISTS \((SELECT .*?)\) THEN', text, re.S):
        if query(db, f'SELECT EXISTS ({condition}) AS collision')[0]['collision']:
            raise ValueError('Merchant NPC collision: ' + condition)
    if query(db, 'SELECT * FROM creature_template_model WHERE CreatureID=900500 AND Idx<>0'):
        raise ValueError('Unexpected merchant model rows')
    plan = []
    keys = {'creature_template': ('entry',), 'creature_template_model': ('CreatureID', 'Idx'), 'creature': ('guid',)}
    inserts = re.findall(r'INSERT INTO (\w+) \(([^)]+)\) VALUES \((.*?)\) ON DUPLICATE KEY UPDATE [^;]+;', text)
    if len(inserts) != 12:
        raise ValueError('Unexpected merchant SQL layout')
    for table, columns, values in inserts:
        cols = columns.split(',')
        desired = query(db, 'SELECT ' + ','.join(f'{v} AS `{c}`' for c, v in zip(cols, values.split(','))))[0]
        where = ' AND '.join(f'`{key}`=%s' for key in keys[table])
        rows = query(db, f'SELECT {columns} FROM `{table}` WHERE {where}', tuple(desired[k] for k in keys[table]))
        if rows:
            for column, value in desired.items():
                actual = rows[0][column]
                same = math.isclose(actual, float(value), rel_tol=0, abs_tol=0.001) if isinstance(actual, float) else actual == value
                if not same:
                    raise ValueError(f'Merchant {table}.{column} differs; no updates permitted')
        else:
            plan.append(f'INSERT INTO `{table}` ({columns}) VALUES ({values})')
    return plan


def encode(value):
    if isinstance(value, bytes):
        return {'hex': value.hex()}
    return str(value) if isinstance(value, (dt.datetime, dt.date)) else value


def data_hashes(db, tables, old_max):
    result = {}
    for database, names in tables.items():
        for name in names:
            where = ''
            if database == 'acore_auth' and name in ('account', 'realmcharacters'):
                where = f' WHERE {"id" if name == "account" else "acctid"}<={old_max}'
            rows = query(db, f'SELECT * FROM `{database}`.`{name}`{where}')
            hashes = sorted(hashlib.sha256(json.dumps(row, default=encode, sort_keys=True,
                                                     separators=(',', ':')).encode()).hexdigest() for row in rows)
            result[f'{database}.{name}'] = dict(rows=len(rows), sha256=hashlib.sha256(''.join(hashes).encode()).hexdigest())
    return result


def backup(password, directory):
    commands = [('characters.sql', ['acore_characters']), ('auth.sql', ['acore_auth'])]
    for table, where in [('creature_template', 'entry=900500'), ('creature_template_model', 'CreatureID=900500'),
                         ('creature', 'id=900500 OR guid BETWEEN 9005000 AND 9005009')]:
        commands.append((f'world-{table}.sql', ['acore_world', table, '--where=' + where]))
    for filename, args in commands:
        with (directory / filename).open('xb') as output:
            subprocess.run(['docker', 'exec', '-e', 'MYSQL_PWD', CONTAINER, 'mysqldump', '-uroot',
                            '--single-transaction', '--skip-lock-tables', '--routines', '--triggers',
                            '--hex-blob', '--no-tablespaces', '--set-gtid-purged=OFF', *args],
                           env={**os.environ, 'MYSQL_PWD': password}, stdout=output, check=True)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.glob('*.sql')}
    (directory / 'dump-sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')


def run(apply=False):
    import pymysql
    password = os.environ.get('WOWPILAGO_TEST_ACCOUNT_PASSWORD', '')
    verifier('APV2A', password, bytes(32))
    db_password = os.environ['WOWPILAGO_DB_PASSWORD']
    sources = {name: (ROOT / 'sql' / name).read_text() for name in ('v2.sql', 'v2_effects.sql', 'world.sql')}
    pb_sources = {p.name: p.read_text() for p in sorted((BUILD / 'source/modules/mod-playerbots/data/sql/playerbots/base').glob('*.sql'))}
    if len(pb_sources) != 29:
        raise ValueError('Missing playerbots base SQL files')
    pb_plan = playerbots_plan(pb_sources)
    source_hashes = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in {**sources, **pb_sources}.items()}
    receipt_path = PRIVATE / 'receipt.json'
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    if receipt and (receipt['sources'] != source_hashes or receipt['uuid'] != UUID):
        raise ValueError('Inputs/DB changed since preparation; review required, no automatic migrations')
    db = pymysql.connect(host='127.0.0.1', port=13317, user='root', password=db_password,
                         autocommit=True, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
    with db:
        guard(db)
        execute(db, 'USE acore_characters')
        missing_accounts = accounts_plan(db, password)
        plan, objects = character_plan(db, sources, receipt)
        execute(db, 'USE acore_world')
        merchant = world_plan(db, sources['world.sql'])
        pb_exists = query(db, 'SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s', (PB,))
        if pb_exists:
            if not receipt.get('playerbots'):
                raise ValueError('Existing acore_playerbots_v2 has no preparation receipt; refusing to touch it')
            for name, definition in receipt['playerbots'].items():
                if object_definition(db, PB, 'TABLE', name) != definition:
                    raise ValueError('Playerbots schema changed: ' + name)
        print(json.dumps(dict(mode='apply' if apply else 'preflight: no writes', new_accounts=missing_accounts,
                              character_ddl=len(plan), merchant_inserts=len(merchant), new_playerbots_db=not bool(pb_exists)), indent=2))
        if not apply:
            return
        if query(db, "SELECT GET_LOCK('wowpilago_private_v2_provision',0) AS acquired")[0]['acquired'] != 1:
            raise ValueError('Another fixture provisioner holds the lock')
        os.umask(0o077)
        directory = PRIVATE / 'backups' / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        directory.mkdir(parents=True)
        tables = {database: [r['TABLE_NAME'] for r in query(db, 'SELECT TABLE_NAME FROM information_schema.TABLES '
                   'WHERE TABLE_SCHEMA=%s AND TABLE_TYPE="BASE TABLE" ORDER BY TABLE_NAME', (database,))]
                  for database in ('acore_auth', 'acore_characters')}
        old_max = query(db, 'SELECT COALESCE(MAX(id),0) AS n FROM acore_auth.account')[0]['n']
        before = data_hashes(db, tables, old_max)
        (directory / 'before.json').write_text(json.dumps(before, indent=2) + '\n')
        backup(db_password, directory)
        guard(db)
        try:
            execute(db, 'USE acore_characters')
            for sql in plan:
                execute(db, sql)
            execute(db, 'USE acore_world')
            db.begin()
            try:
                for sql in merchant:
                    execute(db, sql)
                db.commit()
            except Exception:
                db.rollback()
                raise
            if not pb_exists:
                execute(db, f'CREATE DATABASE `{PB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
                execute(db, f'USE `{PB}`')
                for sql in pb_plan:
                    execute(db, sql)
            add_accounts(db, password, missing_accounts)
            accounts_plan(db, password)
        finally:
            after = data_hashes(db, tables, old_max)
            (directory / 'after.json').write_text(json.dumps(after, indent=2) + '\n')
            if before != after:
                raise ValueError(f'Protected data changed! Inspect {directory}; never auto-restore over shared data')
        receipt = dict(uuid=UUID, sources=source_hashes, backup=str(directory), protected_data_unchanged=True,
                       objects={name: object_definition(db, 'acore_characters', kind, name) for name, kind in objects.items()},
                       playerbots={r['TABLE_NAME']: object_definition(db, PB, 'TABLE', r['TABLE_NAME']) for r in query(db,
                         'SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s', (PB,))})
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
        print(f'ADD-only preparation complete; unchanged protected data: {directory}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Back up first, then add missing fixtures; never start services')
    args = parser.parse_args()
    run(args.apply)
