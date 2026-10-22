"""Fresh native Artisan proof. Default is offline; live use needs a parent release."""
import argparse
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys
from unittest.mock import patch

import verify_runtime as shared
import verify_travel_runtime as travel
from verify_merchant_runtime import MerchantRunner
from verify_class_systems import DBC_DIR
from verify_runtime import Runner, require, guard_account, manifest_fixture, LABEL
from bridge.catalog import Catalog
from bridge.v2 import Store
from tools.build_realm import fingerprints, tree_digest
from tools.validate_checks import DBC
from provision_realm import UUID, check_account

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / '.local/v2-build/20261019T191318.518327Z-mail-fixed'
SOURCE = BUILD / 'source'
OUTPUT = ROOT / '.local/artisan-runtime-plan/fixed-owner-guard'
CPP = '85e1a31476fe3d918dd61bfba685401c520707d72dcc3d4579788c3b4baa83c7'
IMAGE = 'sha256:55bfa1750408af5f5645166e47928aac6ecf0be92dd24005411cd96115f18ed9'
CORE = '9fb906bb7296212ff42fc95ff73a92aaf8554f0d'
BOTS = '2f7d9f774987d0157c6a0d0cc08c40bec3db3945'
MOUNTS = (458, 23227, 32239, 32242, 40192)
ARTISAN = 919100013
PLAN = dict(label=LABEL, network_without_run=False, build=str(BUILD), source_cpp=CPP,
            creates='one fresh marked GM0 APV2B human warrior; reuse proved GM13 only',
            checks=['60 Expert 150% allowed, 280/310 denied', '69 fast denied',
                    '70 same fast spells denied before Artisan; receipt then 26.6/28.7 and saved 280/310 auras',
                    '20/40 ground 60/100% regression'],
            requires='successful pinned build, deployed matching binary, parent owner release.json, all characters offline',
            excluded=['real AP room', 'Druid class switching', 'deployment/restart/config edits',
                      'history reset/deletion', 'SQL gameplay writes', 'airborne movement proof'])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_evidence():
    """Local validation first. Never fall back to a previous successful build."""
    manifest = json.loads((BUILD / 'manifest.json').read_text())
    require(manifest.get('status') == 'success', 'Pinned Artisan build is not successful')
    require(manifest.get('core_commit') == CORE and manifest.get('playerbots_commit') == BOTS
            and manifest.get('image_id') == IMAGE and manifest.get('protocol_version') == 2,
            'Build commits/image/protocol mismatch')
    expected = manifest['module_files_sha256']
    require(expected.get('APProgression.cpp') == CPP, 'Wrong Artisan source hash')
    require(fingerprints(ROOT / 'src') == expected
            and fingerprints(SOURCE / 'modules/mod-archipelago/src') == expected
            and tree_digest(expected) == manifest['module_tree_sha256'], 'Module files differ')
    source_files = json.loads((BUILD / 'source-files.sha256.json').read_text())
    require(tree_digest(source_files) == manifest['source_tree_sha256'], 'Source inventory mismatch')
    # These are the native helpers used by the imported packet/travel implementation.
    for name in ('Entities/Player/Player.cpp', 'Handlers/SpellHandler.cpp',
                 'Handlers/MovementHandler.cpp', 'Spells/Spell.cpp', 'Server/Protocol/Opcodes.h'):
        path = 'src/server/game/' + name
        require(digest(SOURCE / path) == source_files[path], 'Native helper source changed: ' + path)
    for path in ('src/server/scripts/Commands/cs_tele.cpp', 'src/server/scripts/Commands/cs_misc.cpp'):
        require(digest(SOURCE / path) == source_files[path], 'Native command source changed')
    installed = manifest['installed_files_sha256']
    require(fingerprints(BUILD / 'install') == installed, 'Installed build files differ')
    world_hash = installed['bin/worldserver']
    require(len(world_hash) == 64 and all(c in '0123456789abcdef' for c in world_hash), 'Invalid world hash')
    return dict(manifest_sha256=digest(BUILD / 'manifest.json'), world_sha256=world_hash,
                source=str(SOURCE), source_cpp=CPP, core_commit=CORE, playerbots_commit=BOTS,
                image_id=IMAGE, module_files_sha256=expected)


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, timeout=15)


def runtime_evidence(evidence):
    info = json.loads(docker('inspect', 'wow-test-worldserver-1'))[0]
    labels = info['Config']['Labels']
    require(info['State']['Running'] and info['Image'] == IMAGE
            and labels.get('com.docker.compose.project') == 'wow-test'
            and labels.get('com.docker.compose.service') == 'worldserver', 'Wrong live world/image')
    require(any(m['Destination'] == '/work/install' and not m['RW']
                and Path(m['Source']).resolve() == (BUILD / 'install').resolve()
                for m in info['Mounts']), 'World is not mounted from pinned install')
    for path in ('/proc/1/exe', '/work/install/bin/worldserver'):
        require(docker('exec', 'wow-test-worldserver-1', 'sha256sum', path).split()[0]
                == evidence['world_sha256'], 'Old or mismatched runtime: ' + path)
    release = json.loads((OUTPUT / 'release.json').read_text())
    require(all(release.get(k) is True for k in ('owned_release', 'gui40_released', 'mail46_released'))
            and release.get('world_sha256') == evidence['world_sha256'], 'Parent release missing/mismatched')
    return dict(container_id=info['Id'], release=release)


def dbc_evidence():
    dbc = DBC(DBC_DIR / 'Spell.dbc')
    expected = {458: ('Brown Horse', (78, 32, 0), (0, 59, 0)),
                23227: ('Swift Palomino', (78, 32, 0), (0, 99, 0)),
                32239: ('Ebon Gryphon', (78, 207, 32), (0, 149, 59)),
                32242: ('Swift Blue Gryphon', (78, 207, 32), (0, 279, 99)),
                40192: ("Ashes of Al'ar", (78, 207, 32), (0, 309, 99))}
    rows = {}
    for spell, (name, auras, points) in expected.items():
        row = dbc.rows[spell]
        require(dbc.text(row[136]) == name and row[95:98] == auras and row[80:83] == points
                and row[71:74] == ((6, 6, 0) if spell in (458, 23227) else (6, 6, 6)),
                'Actual DBC mount differs: ' + str(spell))
        rows[str(spell)] = dict(name=name, auras=auras, base_points=points, row=row)
    return dict(sha256=hashlib.sha256(dbc.raw).hexdigest(), spells=rows)


def cast_packet(spell, count):
    require(type(spell) is int and spell in MOUNTS and type(count) is int and 0 <= count < 256,
            'Only bounded ordinary self mount casts')
    return struct.pack('<BIBI', count, spell, 0, 0)


def guard_receipts(rows, codes, prior):
    require(rows[:len(prior)] == prior
            and [r['item_index'] for r in rows] == list(range(len(codes)))
            and [r['ap_item'] for r in rows] == codes and all(r['applied'] == 1 for r in rows),
            'Receipt history changed or not contiguous/applied')


@dataclass
class FixtureOwner:
    """Creation is reserved before authentication, and never retried after an attempt."""
    reserved: bool = False

    def reserve(self, row, count):
        guard_account(row, 'APV2B')
        require(type(row['id']) is int and row['id'] > 1 and type(count) is int and 0 <= count < 10,
                'Wrong account ID or no private capacity')
        require(not self.reserved, 'Fresh fixture creation already reserved')
        self.reserved = True


class ArtisanRunner(travel.TravelRunner):
    reuse_control = MerchantRunner.reuse_control

    def __init__(self, db):
        Runner.__init__(self, db, 'APV2B')
        self.owner = FixtureOwner()
        self.codes, self.checks = [], []
        self.store = self.guid = None
        self.level, self.count = 1, 0
        self.receipts = []

    @contextmanager
    def login(self, account, *, guid=None):
        require(account in ('APV2B', 'TEST'), 'Protected account')
        if guid is None:
            require(account == 'APV2B', 'Never create TEST')
            row = self.account_row(account)
            count = self.query('SELECT COUNT(*) AS n FROM acore_characters.characters WHERE account=%s', (row['id'],))[0]['n']
            self.owner.reserve(row, count)
        else:
            require(guid in self.known and guid > 4
                    and guid == (13 if account == 'TEST' else self.guid), 'Not owned fresh fixture/control')
        with Runner.login(self, account, guid=guid) as result:
            yield result

    def cast(self, player, spell, **kwargs):
        for mount in MOUNTS:
            player.send(0x136, struct.pack('<I', mount))  # Ordinary self aura cancellation, no state writes.
        player.stay(.3)
        # Reuse the checked native response assertions, extending only the ordinary mount allowlist.
        with patch.object(travel, 'cast_packet', cast_packet):
            return travel.TravelRunner.cast(self, player, spell, **kwargs)

    def setup(self, gm, command):
        allowed = {'.learn ' + str(s) for s in MOUNTS}
        allowed.update('.levelup ' + self.names[self.guid] + ' ' + str(n - self.level)
                       for n in (20, 40, 60, 69, 70) if n > self.level)
        allowed.update('.tele name ' + self.names[self.guid] + ' ' + d
                       for d in ('Stormwind', 'HellfirePeninsula'))
        require(command in allowed, 'Only forward setup and ordinary mount learning allowed')
        super().setup(gm, command)

    def state(self, label):
        state = super().state(label)
        rows = state['rewards']
        guard_receipts(rows, self.codes, self.receipts)
        self.receipts = rows
        binding = self.query('SELECT * FROM acore_characters.mod_archipelago_binding WHERE id=%s', (self.binding,))
        require([{k: v for k, v in r.items() if k not in ('status', 'heartbeat')} for r in binding]
                == self.original_binding, 'Immutable binding changed')
        skill = self.query('SELECT * FROM acore_characters.character_skills WHERE guid=%s AND skill=762', (self.guid,))
        travel.emit('native_state', guid=self.guid, label=label, skill=skill,
                    progress=state['progress'], receipts=rows, binding=binding, item_count=len(state['items']))
        return state, skill

    def preflight(self):
        require(self.query('SELECT @@server_uuid AS uuid') == [dict(uuid=UUID)], 'Wrong private database')
        row = self.account_row('APV2B')
        guard_account(row, 'APV2B')
        private = self.query('SELECT email,reg_mail,salt,verifier FROM acore_auth.account WHERE id=%s', (row['id'],))
        require(len(private) == 1, 'Missing private account')
        check_account(private[0], 'APV2B', os.environ['WOWPILAGO_TEST_ACCOUNT_PASSWORD'])
        existing = self.query('SELECT guid,name,race,class,level,online FROM acore_characters.characters WHERE account=%s ORDER BY guid', (row['id'],))
        require(len(existing) == 3 and all(r['online'] == 0 and r['guid'] > 4 for r in existing),
                'Expected three existing offline fixtures and private capacity')
        online = self.query('SELECT guid FROM acore_characters.characters WHERE online<>0')
        require(not online, 'All characters must be offline before owned fixture creation')
        travel.emit('account_preflight', account=row, existing_characters=existing, online=online)

    def protected(self):
        result = super().protected()
        result['original_skills'] = self.query(
            'SELECT * FROM acore_characters.character_skills WHERE guid IN (1,2,3) ORDER BY guid')
        for table in ('characters', 'character_spell', 'character_talent', 'character_aura', 'character_inventory', 'character_skills'):
            result['window4_' + table] = self.query('SELECT * FROM acore_characters.' + table + ' WHERE guid=4')
            result['existing_APV2B_' + table] = self.query(
                'SELECT * FROM acore_characters.' + table + ' WHERE guid IN '
                '(SELECT guid FROM acore_characters.characters WHERE account='
                '(SELECT id FROM acore_auth.account WHERE username=%s) AND guid<>%s) ORDER BY guid',
                ('APV2B', self.guid or 0))
        return result

    def execute(self):
        self.preflight()
        control = self.reuse_control()  # Must precede the fresh creation path.
        catalog = Catalog()
        seed = 'private-fabricated-artisan-proof-' + secrets.token_hex(12)
        raw = manifest_fixture(catalog, seed)
        (OUTPUT / 'manifest.json').write_text(json.dumps(raw, indent=2))
        with self.login('APV2B') as (_, self.guid):
            creation = dict(guid=self.guid, name=self.names[self.guid], account=self.account, label=LABEL)
            (OUTPUT / 'creation.json').write_text(json.dumps(creation, indent=2))
            travel.emit('fixture_created', **creation)
        fresh = self.offline(self.guid)
        require(fresh['level'] == 1 and fresh['race'] == fresh['class'] == 1
                and not self.query('SELECT id FROM acore_characters.mod_archipelago_binding WHERE character_guid=%s', (self.guid,)),
                'Not fresh unbound human warrior; never reset history')
        self.store = Store(dict(host='127.0.0.1', port=13317, user='root', database='acore_characters'), self.guid, catalog)
        self.binding = self.store.bind(seed, 0, 1, raw)
        self.store.status('disconnected')
        binding = self.query('SELECT * FROM acore_characters.mod_archipelago_binding WHERE id=%s', (self.binding,))
        require(len(binding) == 1, 'Missing new binding')
        self.original_binding = [{k: v for k, v in r.items() if k not in ('status', 'heartbeat')} for r in binding]
        travel.emit('binding', guid=self.guid, binding=self.binding, seed=seed, label=LABEL)
        with self.login('TEST', guid=control) as (gm, _):
            with self.login('APV2B', guid=self.guid) as (player, _):
                for spell in MOUNTS:
                    self.setup(gm, '.learn ' + str(spell))
                self.queue(player, gm, *([919100001] * 7), 919100010, 919100011, 919100012, 919100002)
                self.teleport(player, gm, 'Stormwind', 0)
                self.advance(player, gm, 20)
                self.cast(player, 458, speed=11.2)
                self.advance(player, gm, 40)
                self.cast(player, 23227, speed=14.0)
                self.advance(player, gm, 60)
                self.teleport(player, gm, 'HellfirePeninsula', 530)
                self.cast(player, 32239, speed=17.5)
                for spell in (32242, 40192):
                    self.cast(player, spell, error=107)
            expert, skill = self.state('60 Expert without Artisan')
            require(expert['progress'][0]['riding_flags'] == 7 and skill == [dict(guid=self.guid, skill=762, value=225, max=225)], 'Expert state differs')
            for level in (69, 70):
                with self.login('APV2B', guid=self.guid) as (player, _):
                    self.advance(player, gm, level)
                    for spell in (32242, 40192):
                        self.cast(player, spell, error=107)
                before, skill = self.state(str(level) + ' no Artisan, same fast spells denied')
                require(before['progress'][0]['riding_flags'] == 7 and skill[0]['value'] == 225
                        and 34091 not in {r['spell'] for r in before['spells']}, 'Premature Artisan')
            with self.login('APV2B', guid=self.guid) as (player, _):
                self.queue(player, gm, ARTISAN)
            trained, skill = self.state('70 native Artisan receipt')
            require(trained['progress'][0]['riding_flags'] == 15
                    and trained['progress'][0]['riding_flags'] & 12 == 12
                    and 34091 in {r['spell'] for r in trained['spells']}
                    and skill == [dict(guid=self.guid, skill=762, value=300, max=300)], 'Native Artisan training missing')
            for spell, speed, aura in ((32242, 26.6, 280), (40192, 28.7, 310)):
                with self.login('APV2B', guid=self.guid) as (player, _):
                    self.cast(player, spell, speed=speed)
                after, _ = self.state('70 Artisan saved aura ' + str(aura))
                require(any(r['spell'] == spell and r['amount1'] == aura for r in after['auras']), 'Saved native flight aura missing')
                require(after['inventory'] == expert['inventory'] and after['items'] == expert['items'], 'Mount test changed items')
        self.offline(control)
        require(self.codes[-1] == ARTISAN and self.codes.count(ARTISAN) == 1, 'Not exactly one Artisan receipt')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(PLAN, indent=2))
        return 0
    evidence = build_evidence()  # All binary/source/release guards precede DB connection and authentication.
    runtime = runtime_evidence(evidence)
    dbc = dbc_evidence()
    require(os.environ.get('WOWPILAGO_TEST_ACCOUNT_PASSWORD') == 'test-only'
            and os.environ.get('WOWPILAGO_DB_PASSWORD') == 'test-only', 'Private credentials required')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / 'attempt.json').open('x') as handle:
        json.dump(dict(plan=PLAN, evidence=evidence, runtime=runtime), handle, indent=2)
    import pymysql
    with (OUTPUT / 'run.jsonl').open('x', buffering=1) as log, redirect_stdout(log):
        travel.emit('source_binary_evidence', **evidence, runtime=runtime, dbc=dbc)
        with pymysql.connect(host='127.0.0.1', port=13317, user='root', password='test-only', autocommit=True,
                             cursorclass=pymysql.cursors.DictCursor, connect_timeout=5, read_timeout=15, write_timeout=15) as db:
            runner = ArtisanRunner(db)
            runner.preflight()
            before = runner.protected()
            (OUTPUT / 'before.json').write_text(json.dumps(before, default=str, indent=2))
            result = dict(event='FAIL')
            try:
                with patch.object(shared, 'SmokeClient', travel.TravelClient):
                    runner.execute()
                result = dict(event='PASS')
            except Exception as exc:
                result['error'] = str(exc)
            finally:
                if runner.store is not None:
                    runner.store.close()
                after = runner.protected()
                (OUTPUT / 'after.json').write_text(json.dumps(after, default=str, indent=2))
                if before != after:
                    result = dict(event='FAIL', error='Protected originals changed')
                travel.emit('protected_assertion', guids=[1, 2, 3, 4], existing_APV2B_fixtures=True,
                            unchanged=before == after, guid4='protected only during this later owned window')
                summary = dict(result=result, guid=runner.guid, checks=runner.checks, evidence=evidence,
                               protected_unchanged=before == after, label=LABEL)
                (OUTPUT / 'summary.json').write_text(json.dumps(summary, indent=2))
                travel.emit('artisan_result', **summary)
    return 0 if result['event'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
