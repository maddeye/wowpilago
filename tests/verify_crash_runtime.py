"""Two bounded WORLD PROCESS crash/restart checks. Default is an offline plan."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import uuid

from verify_runtime import Runner, guard_account, manifest_fixture, require, LABEL
from realm_client import ProtocolError, SMSG_AUTH_CHALLENGE
from bridge.catalog import Catalog

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '.local/crash-runtime-plan'
BUILD = ROOT / '.local/v2-build/20261019T191318.518327Z-mail-fixed'
SOURCE = BUILD / 'source'
WORLD_HASH = '3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809'
WORLD = 'wow-test-worldserver-1'
IMAGE = 'sha256:55bfa1750408af5f5645166e47928aac6ecf0be92dd24005411cd96115f18ed9'
CODES = (919100040, 919100033)
PLAN = dict(label=LABEL, kind='WORLD PROCESS crash/restart', network_without_run=False,
            fixture='one fresh marked GM0 APV2B human warrior, reused only within this invocation',
            windows=['offline durable bag/voucher queue -> world SIGKILL -> docker start -> apply once',
                     'online second bag/voucher applied DB proof -> abrupt socket close + world SIGKILL -> start -> relog'],
            excluded=['deterministic COMMIT-before-publication window', 'AP bridge process crash',
                      'legitimate playthrough', 'SQL-only rollback tests'],
            guard='--run --release FILE; fresh <=15 minute parent maintenance release, all characters/accounts offline; all owners released, unrelated bindings disconnected, exact frozen pending digest')

# Parent uses this same read-only query and helper before any fixture is created.
FROZEN_PENDING_SQL = 'SELECT * FROM acore_characters.mod_archipelago_reward WHERE applied=0'


def frozen_pending_digest(rows):
    canonical = sorted(json.dumps(row, default=str, sort_keys=True, separators=(',', ':'),
                                  ensure_ascii=True) for row in rows)
    return hashlib.sha256(('[' + ','.join(canonical) + ']').encode('utf-8')).hexdigest()


def verify_frozen_pending(rows, release):
    require(frozen_pending_digest(rows) == release['frozen_pending_sha256'],
            'Frozen pending history changed or was not fully attested')


def verify_protected(before, after, release):
    for snapshot in (before, after):
        verify_frozen_pending([r for r in snapshot.get('mod_archipelago_reward', [])
                               if r['applied'] == 0], release)
    require(before == after, 'Preexisting characters or AP history changed')


def save(path, value):
    path.write_text(json.dumps(value, default=str, sort_keys=True, indent=2) + '\n')


def command(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=20).strip()


def inspect(name):
    return json.loads(command('docker', 'inspect', name))[0]


def validate_release(value, now):
    require(value.get('world') == WORLD and value.get('image') == IMAGE,
            'Release targets wrong runtime')
    require(type(value.get('issued_at')) in (int, float) and 0 <= now - value['issued_at'] <= 900,
            'Parent release must be issued within 15 minutes')
    for key in ('all_agents_released', 'normal_ap_journey_offline', 'exclusive_maintenance'):
        require(value.get(key) is True, 'Parent must attest ' + key)
    require(isinstance(value.get('world_id'), str) and len(value['world_id']) == 64,
            'Release requires full current Docker container ID')
    digest = value.get('frozen_pending_sha256')
    require(isinstance(digest, str) and len(digest) == 64
            and all(c in '0123456789abcdef' for c in digest),
            'Release requires frozen_pending_sha256 for every previous unapplied row')
    guids = value.get('offline_guids')
    require(isinstance(guids, list) and all(type(g) is int and g > 0 for g in guids)
            and set(range(1, 5)) <= set(guids) and len(set(guids)) == len(guids),
            'Release must enumerate every existing GUID, including 1..4')


def no_other_runners():
    """Additional local check, not a substitute for the parent's exclusive window."""
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if not args or 'python' not in Path(os.fsdecode(args[0])).name:
            continue
        names = [Path(os.fsdecode(arg)).name for arg in args[1:] if arg]
        require(not any(n.startswith(('verify_', 'gui_', 'run_v2_bridge', 'provision_realm'))
                        and n.endswith('.py') for n in names),
                'Another runtime/GUI/bridge/provisioning process exists: ' + proc.name)


def source_evidence():
    manifest = json.loads((BUILD / 'manifest.json').read_text())
    require(manifest['image_id'] == IMAGE and manifest['installed_files_sha256']['bin/worldserver'] == WORLD_HASH,
            'Build manifest pin mismatch')
    hashes = manifest['module_files_sha256']
    for name, digest in hashes.items():
        for path in (ROOT / 'src' / name, SOURCE / 'modules/mod-archipelago/src' / name):
            require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'Module pin mismatch: ' + str(path))
    require(hashlib.sha256((BUILD / 'install/bin/worldserver').read_bytes()).hexdigest() == WORLD_HASH,
            'Mounted world binary changed')
    return dict(world_sha256=WORLD_HASH, image=IMAGE, modules=hashes)


def runtime_identity(info):
    require(info['Name'] == '/' + WORLD and info['Image'] == IMAGE, 'Wrong world container/image')
    require(info['Config']['Entrypoint'] == ['/work/install/bin/worldserver']
            and info['Config']['Cmd'] == ['-c', '/work/install/etc/worldserver.conf'], 'Wrong world command')
    require(info['HostConfig']['RestartPolicy']['Name'] == 'no',
            'Restart policy must already be no; verifier will not change it')
    mounts = info['Mounts']
    require(any(m['Destination'] == '/work/install' and not m['RW']
                and Path(m['Source']).resolve() == (BUILD / 'install').resolve() for m in mounts),
            'Wrong installed binary mount')
    return {k: info[k] for k in ('Id', 'Image', 'Mounts', 'Config', 'HostConfig')}


def read_world_challenge(timeout=2):
    """Receive only the full unencrypted challenge; never send authentication bytes."""
    deadline = time.monotonic() + timeout
    with socket.create_connection(('127.0.0.1', 8085), timeout=timeout) as sock:
        packet = bytearray()
        for end in (4, 44):
            while len(packet) < end:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise socket.timeout('World challenge timeout')
                sock.settimeout(remaining)
                part = sock.recv(end - len(packet))
                if not part:
                    raise EOFError('World challenge connection closed')
                packet.extend(part)
            if end == 4 and (int.from_bytes(packet[:2], 'big') != 42
                             or int.from_bytes(packet[2:4], 'little') != SMSG_AUTH_CHALLENGE):
                raise ProtocolError('Invalid world challenge size/opcode: ' + packet.hex())
        return bytes(packet)


class CrashRunner(Runner):
    def __init__(self, db, output, release):
        super().__init__(db, 'APV2B')
        self.output, self.release = output, release
        self.guid = self.binding = self.store = None
        self.created = False
        self.crashes = 0
        self.initial = runtime_identity(inspect(WORLD))
        require(self.initial['Id'] == release['world_id'], 'Released world has been replaced')
        self.companions = {n: inspect(n) for n in ('wow-test-authserver-1', 'wow-test-database-1')}
        for info in self.companions.values():
            require(info['State']['Running'], 'Auth/database must already be running')

    def exclusive(self):
        validate_release(self.release, time.time())
        no_other_runners()
        allowed = () if self.guid is None else (self.guid,)
        online = self.query('SELECT guid FROM acore_characters.characters WHERE online<>0')
        require(all(r['guid'] in allowed for r in online), 'Unrelated character online')
        account = self.account_row('APV2B')
        online_accounts = self.query('SELECT id FROM acore_auth.account WHERE online<>0')
        require(all(self.guid is not None and r['id'] == account['id'] for r in online_accounts),
                'Unrelated account online')
        require(not self.query("SELECT id FROM acore_characters.mod_archipelago_binding WHERE status<>'disconnected'"),
                'AP binding is not disconnected')
        pending = self.query(FROZEN_PENDING_SQL)
        if self.binding is not None:
            require(self.guid is not None and self.guid not in self.release['offline_guids'],
                    'Frozen history cannot be an owned fixture')
            owners = self.query('SELECT character_guid FROM acore_characters.mod_archipelago_binding WHERE id=%s',
                                (self.binding,))
            require(owners == [dict(character_guid=self.guid)], 'Owned binding is not the fresh fixture')
            pending = [r for r in pending if r['binding_id'] != self.binding]
        verify_frozen_pending(pending, self.release)
        roster = {r['guid'] for r in self.query('SELECT guid FROM acore_characters.characters')}
        require(roster == set(self.release['offline_guids']) | set(allowed), 'Character roster changed')
        for guid in roster - set(allowed):
            name = 'wowpilago:' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'acore_characters:' + str(guid)))
            require(self.query('SELECT IS_USED_LOCK(%s) AS owner', (name,))[0]['owner'] is None,
                    'An unrelated Store/bridge still owns GUID ' + str(guid))

    @contextmanager
    def login(self, account='APV2B', *, guid=None):
        require(account == 'APV2B', 'Only APV2B login permitted, never TEST or journey')
        self.exclusive()
        if guid is None:
            require(not self.created, 'Only one creation per invocation')
            row = self.account_row(account)
            guard_account(row, account)
            count = self.query('SELECT COUNT(*) AS n FROM acore_characters.characters WHERE account=%s', (row['id'],))[0]['n']
            require(0 <= count < 10, 'No free APV2B character slot')
            self.created = True
        else:
            require(guid == self.guid and guid in self.known and guid > 4, 'Not the fresh owned GUID')
        with super().login(account, guid=guid) as result:
            if guid is None:
                self.guid = result[1]
                require(self.guid > 4, 'Protected GUID')
                save(self.output / 'creation.json', dict(guid=self.guid, name=self.names[self.guid], account=account))
            try:
                yield result
            finally:
                self.exclusive()

    def state(self, label):
        self.exclusive()
        state = {key: list(rows) for key, rows in self.snapshot(self.guid, self.binding).items()}
        state['binding'] = self.query('SELECT * FROM acore_characters.mod_archipelago_binding WHERE id=%s', (self.binding,))
        owned = self.query('SELECT guid FROM acore_characters.item_instance WHERE owner_guid=%s ORDER BY guid', (self.guid,))
        require([r['guid'] for r in owned] == [r['guid'] for r in state['items']], 'Orphan/foreign owned item detected')
        for key, table in (('checks', 'mod_archipelago_check'), ('boss_credit', 'mod_archipelago_boss_credit'),
                           ('enabled_checks', 'mod_archipelago_enabled_check'), ('allowed_rewards', 'mod_archipelago_allowed_reward')):
            state[key] = sorted(self.query('SELECT * FROM acore_characters.' + table + ' WHERE binding_id=%s',
                                           (self.binding,)), key=lambda row: json.dumps(row, default=str, sort_keys=True))
        # Native playedTime is elapsed online time, not a reward effect.
        for item in state['items']:
            item.pop('playedTime', None)
        save(self.output / (label + '.json'), state)
        return state

    def protected(self):
        """Snapshot existing private data; no credentials or auth session keys."""
        result = {}
        tables = self.query('SELECT TABLE_NAME AS name FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s', ('acore_characters',))
        for row in tables:
            table = row['name']
            require(table.replace('_', '').isalnum(), 'Unsafe table name')
            if table.startswith('mod_archipelago_'):
                column = 'id' if table == 'mod_archipelago_binding' else 'binding_id'
                rows = self.query('SELECT * FROM acore_characters.' + table)
                rows = [r for r in rows if column not in r or r[column] != self.binding]
            elif table in ('characters', 'item_instance') or table.startswith('character_'):
                column = {'characters': 'guid', 'item_instance': 'owner_guid',
                          'character_pet': 'owner', 'character_pet_declinedname': 'owner'}.get(table, 'guid')
                columns = self.query('SELECT COLUMN_NAME AS name FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s', ('acore_characters', table))
                if column not in {c['name'] for c in columns}:
                    continue
                rows = self.query('SELECT * FROM acore_characters.' + table)
                rows = [r for r in rows if r[column] != self.guid]
            else:
                continue
            result[table] = sorted(rows, key=lambda r: json.dumps(r, default=str, sort_keys=True))
        return result

    def health(self):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            info = inspect(WORLD)
            if info['State']['Running']:
                try:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise socket.timeout('World readiness deadline reached')
                    read_world_challenge(timeout=min(2, remaining))
                except (OSError, EOFError):
                    pass
                else:
                    break
            time.sleep(min(.5, max(0, deadline - time.monotonic())))
        else:
            raise RuntimeError('World readiness timeout, preserve container and logs')
        require(runtime_identity(info) == self.initial, 'Restart changed world identity/config/mounts')
        require(command('docker', 'exec', WORLD, 'sha256sum', '/proc/1/exe').split()[0] == WORLD_HASH,
                'Restart binary mismatch')
        for name, before in self.companions.items():
            after = inspect(name)
            require(after['Id'] == before['Id'] and after['State']['Running']
                    and after['State']['StartedAt'] == before['State']['StartedAt'], 'Auth/database restarted')
        save(self.output / ('runtime-' + str(self.crashes) + '.json'), info)

    def crash(self, player=None):
        self.exclusive()
        require(self.crashes < 2, 'Only two world kills allowed')
        require(runtime_identity(inspect(WORLD)) == self.initial, 'Runtime changed before kill')
        if player is not None:
            require(self.character(self.guid)['online'] == 1, 'Applied window requires owned online player')
            # Shared context still verifies offline afterwards, but must not send a clean logout.
            player.logout = lambda: None
            player.sock.close()
        self.crashes += 1
        command('docker', 'kill', '--signal=SIGKILL', WORLD)
        dead = inspect(WORLD)
        save(self.output / ('killed-' + str(self.crashes) + '.json'), dead)
        require(not dead['State']['Running'] and dead['State']['ExitCode'] == 137, 'No confirmed SIGKILL exit')
        command('docker', 'start', WORLD)  # Never compose up, recreate, rebuild, or a mutable tag.
        self.health()
        if self.guid is not None:
            self.offline(self.guid)
        self.exclusive()

    def queue(self, start):
        self.exclusive()
        records = [dict({'class': 'NetworkItem'}, item=code, location=-1, player=0, flags=0) for code in CODES]
        require(self.store.receive(start, records), 'Synthetic Store ingress rejected')
        self.exclusive()

    def applied(self, player, count):
        self.exclusive()
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            rows = self.query('SELECT applied FROM acore_characters.mod_archipelago_reward WHERE binding_id=%s', (self.binding,))
            if len(rows) == count and all(r['applied'] for r in rows):
                self.exclusive()
                return
            player.stay(.2)
        raise RuntimeError('Applied receipt timeout')

    def execute(self):
        from bridge.v2 import Store
        self.exclusive()
        self.health()
        catalog = Catalog()
        seed = 'fabricated-world-crash-' + secrets.token_hex(12)
        raw = manifest_fixture(catalog, seed)
        save(self.output / 'manifest.json', raw)
        with self.login():
            pass
        row = self.offline(self.guid)
        require(row['level'] == 1 and row['xp'] == 0, 'Not a fresh level-1 fixture')
        require(not self.query('SELECT id FROM acore_characters.mod_archipelago_binding WHERE character_guid=%s', (self.guid,)),
                'Never reset existing binding/history')
        self.store = Store(dict(host='127.0.0.1', port=13317, user='root', database='acore_characters'), self.guid, catalog)
        self.binding = self.store.bind(seed, 0, 1, raw)
        self.store.status('disconnected')
        baseline = self.state('baseline')
        self.queue(0)
        queued = self.state('queued-offline')
        verify_queued(baseline, queued)
        self.crash()
        require(self.state('queued-after-restart') == queued, 'Offline queue changed during restart')
        with self.login(guid=self.guid) as (player, _):
            self.applied(player, 2)
        first = self.state('first-applied-offline')
        verify_effects(baseline, first, 1, self.guid, self.binding)
        with self.login(guid=self.guid) as (player, _):
            require(self.state('first-relog-proof') == first, 'First applied batch changed across relog')
            self.queue(2)
            self.applied(player, 4)
            online = self.state('second-applied-online-proof')
            verify_effects(baseline, online, 2, self.guid, self.binding)
            require(online['checks'] == first['checks'], 'Unmoving second batch changed native checks')
            self.crash(player)
        require(self.state('second-after-restart') == online, 'Applied DB state changed during crash/restart')
        for index in range(2):
            with self.login(guid=self.guid) as (player, _):
                player.stay(7)  # More than the native five-second delivery poll.
            final = self.state('relog-' + str(index))
            require(final == online, 'Relog changed durable receipt/inventory/progress/check state')
            verify_effects(baseline, final, 2, self.guid, self.binding)


def verify_queued(before, queued):
    rows = queued['rewards']
    require(not before['rewards'] and len(rows) == 2 and [r['item_index'] for r in rows] == [0, 1]
            and [r['ap_item'] for r in rows] == list(CODES)
            and [(r['kind'], r['value']) for r in rows] == [('bag', 21841), ('vouchers', 5)]
            and all(r['binding_id'] == before['binding'][0]['id'] and r['sender'] == 0
                    and r['location_id'] == -1 and r['flags'] == 0 and not r['applied']
                    and r['applied_value'] == 0 and r['item_guid'] is None
                    and r['applied_at'] is None for r in rows), 'Not the exact durable pending queue')
    require({k: v for k, v in before.items() if k != 'rewards'}
            == {k: v for k, v in queued.items() if k != 'rewards'}, 'Queue caused premature effects')


def verify_effects(before, after, batches, guid, binding):
    rewards = after['rewards']
    require(len(rewards) == batches * 2, 'Extra/missing receipts')
    bags = []
    for index, row in enumerate(rewards):
        bag = index % 2 == 0
        require(row['binding_id'] == binding and row['item_index'] == index
                and row['ap_item'] == CODES[index % 2] and row['kind'] == ('bag' if bag else 'vouchers')
                and row['value'] == (21841 if bag else 5) and row['sender'] == 0
                and row['location_id'] == -1 and row['flags'] == 0 and row['applied'] == 1
                and row['applied_value'] == (1 if bag else 5) and row['applied_at'] is not None,
                'Receipt payload/effect mismatch')
        if bag:
            require(type(row['item_guid']) is int and row['item_guid'] > 0, 'Bag GUID missing')
            bags.append(row['item_guid'])
        else:
            require(row['item_guid'] is None, 'Voucher produced a physical item')
    require(len(set(bags)) == batches, 'Duplicate physical GUID')
    expected_progress = [dict(r) for r in before['progress']]
    require(len(expected_progress) == 1, 'Missing progress')
    expected_progress[0]['vouchers'] += 5 * batches
    require(after['progress'] == expected_progress, 'Extra/missing progress effects')
    added = [r for r in after['items'] if r['guid'] not in {i['guid'] for i in before['items']}]
    require({r['guid'] for r in added} == set(bags) and len(added) == batches, 'Extra/missing physical items')
    for item in added:
        require(item['owner_guid'] == guid and item['itemEntry'] == 21841 and item['count'] == 1
                and item['flags'] == 1, 'Bag ownership/count/bindflags mismatch')
        placement = [r for r in after['inventory'] if r['item'] == item['guid']]
        require(len(placement) == 1 and placement[0]['bag'] == 0 and 23 <= placement[0]['slot'] < 39,
                'Bag must be placed once in backpack')
    require(after['authorized'] == sorted(before['authorized'] +
            [dict(item_guid=g, binding_id=binding, item_entry=21841) for g in bags], key=lambda r: r['item_guid']),
            'Per-GUID authorization mismatch')
    for key in ('binding', 'character', 'abilities', 'purchases', 'stock', 'spells', 'boss_credit', 'enabled_checks', 'allowed_rewards'):
        require(after[key] == before[key], 'Unexpected effect: ' + key)
    require([r for r in after['items'] if r['guid'] not in bags] == before['items']
            and [r for r in after['inventory'] if r['item'] not in bags] == before['inventory'],
            'Existing inventory changed')
    # shortcut: login may record native starting-area checks; compare their exact rows across later relogs.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--release', type=Path)
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(PLAN, indent=2))
        return 0
    require(args.release is not None, '--run requires --release FILE from the parent')
    release = json.loads(args.release.read_text())
    validate_release(release, time.time())
    require(os.environ.get('WOWPILAGO_TEST_ACCOUNT_PASSWORD') == 'test-only'
            and os.environ.get('WOWPILAGO_DB_PASSWORD') == 'test-only', 'Private test-only credentials required')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / 'maintenance.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        no_other_runners()
        run = OUTPUT / ('run-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + secrets.token_hex(4))
        run.mkdir(mode=0o700)
        save(run / 'release.json', release)
        save(run / 'source.json', source_evidence())
        import pymysql
        started = str(int(time.time()))
        result = dict(event='FAIL', label=LABEL, kind=PLAN['kind'])
        with pymysql.connect(host='127.0.0.1', port=13317, user='root', password='test-only',
                             autocommit=True, cursorclass=pymysql.cursors.DictCursor,
                             connect_timeout=5, read_timeout=15, write_timeout=15) as db:
            runner = CrashRunner(db, run, release)
            runner.exclusive()
            before = runner.protected()
            verify_protected(before, before, release)
            save(run / 'protected-before.json', before)
            try:
                runner.execute()
                require(runner.crashes == 2, 'Both world-process windows must complete')
                result['event'] = 'PASS'
            except Exception as exc:
                result['error'] = str(exc)
                if isinstance(exc, subprocess.CalledProcessError):
                    result['command_output'] = exc.output
            finally:
                if runner.store is not None:
                    runner.store.close()
                try:
                    after = runner.protected()
                    save(run / 'protected-after.json', after)
                    verify_protected(before, after, release)
                    runner.exclusive()
                    result['protected_unchanged'] = True
                except Exception as exc:
                    result.update(event='FAIL', protected_unchanged=False, protection_error=str(exc))
                result.update(guid=runner.guid, binding=runner.binding, world_kills=runner.crashes)
                save(run / 'summary.json', result)
                try:
                    (run / 'world.log').write_text(command('docker', 'logs', '--since', started, '--tail', '1000', WORLD))
                except Exception as exc:
                    save(run / 'log-error.json', str(exc))
        print(json.dumps(dict(result, artifacts=str(run)), sort_keys=True))
        return 0 if result['event'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
