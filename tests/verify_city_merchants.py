"""Ten-city personal-stock proof. Default is source-only with zero live observations."""
import argparse
import csv
import math
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import struct
import sys
import time

import verify_artisan_runtime as artisan
import verify_transfer_runtime as transfer
from verify_class_matrix import protected_snapshot
from verify_merchant_runtime import MerchantRunner
from verify_runtime import Runner, guard_account, guard_character, require, say_packet
from verify_travel_runtime import TravelClient
from bridge.catalog import canonical
from provision_realm import UUID, check_account
from tools.validate_checks import DBC

ROOT = artisan.ROOT
OUTPUT = ROOT / '.local/city-merchants-plan/map-control-reviewed'
CASE7 = '.local/class-matrix-plan/third-reviewed-run/attempt-ec4bda0bfebd4870253b7396/class-7/'
OWNERS = {24: ('APV2F', 7, 'Apsfjnnrfebe', 1, 1, 77, 14),
          37: ('APV2C', 4, 'Apsflewguljo', 2, 7, 32, 27)}
CITIES = {24: (0, 1, 2, 3, 8, 9), 37: (4, 6, 5, 7)}
CITY_AREAS = (1519, 1537, 1657, 3557, 1637, 1497, 1638, 3487, 3703, 4395)
CONTROL_ANCHORS = {0: 0, 1: 2, 530: 8, 571: 9}
TELE_COLUMNS = ('id', 'position_x', 'position_y', 'position_z', 'orientation', 'map', 'name')
TELE_SQL = artisan.SOURCE / 'data/sql/base/db_world/game_tele.sql'
XP_TABLE = artisan.SOURCE / 'data/sql/base/db_world/exploration_basexp.sql'
BOOKKEEPING = {'totaltime', 'leveltime', 'logout_time', 'is_logout_resting', 'rest_bonus', 'latency'}
TRAVEL_FIELDS = {'map', 'position_x', 'position_y', 'position_z', 'orientation', 'zone', 'exploredZones'}
PLAN = dict(status='PREP_ONLY', live_observations=0, network_without_run=False,
            actors={24: 'native 30/actor in six cities', 37: 'native 30/actor in four cities'},
            stock_range=[30, 120], configured_default=60, budget_seconds=1800,
            xp_policy='13: four friendly anchor ancestries, at most three native 55-XP credits, total <=220; 24/37: current actor city; exact saved sums and unchanged levels',
            excludes=['stock GUI proof', 'level-1 full-60 UI proof', 'real AP ingress', 'purchases'],
            release='future parent release only; native_matrix_released plus all owners released and offline')


def load(path):
    return json.loads((ROOT / path).read_text())


def save(name, value):
    (OUTPUT / name).write_text(json.dumps(value, indent=2, default=str) + '\n')


def immutable_binding(row):
    return json.loads(json.dumps({k: v for k, v in row.items() if k not in ('status', 'heartbeat')}, default=str))


def character_projection(row):
    if row['guid'] not in (13, 24, 37):
        return dict(row)
    result = {k: v for k, v in row.items() if k not in BOOKKEEPING | TRAVEL_FIELDS}
    result['playerFlags'] &= ~0x20  # Capital-city resting only; preserve every other player flag.
    return result


def spawns():
    text = (ROOT / 'sql/world.sql').read_text()
    values = re.findall(r'VALUES \((900500\d),900500,(\d+),([^,]+),([^,]+),([^,]+),([^,]+),120,', text)
    require(len(values) == 10, 'Expected exactly ten source spawns')
    names = re.findall(r'-- (\w+): game_tele.id=', text)
    require(len(names) == 10, 'Expected ten named source spawns')
    return [dict(guid=int(v[0]), id=900500, map=int(v[1]), position_x=float(v[2]),
                 position_y=float(v[3]), position_z=float(v[4]), orientation=float(v[5]), city=name)
            for v, name in zip(values, names)]


def tele_rows(text):
    # shortcut: fixed pinned dump tuples only; revisit if the upstream dump format changes.
    header, = re.findall(r'CREATE TABLE `game_tele` \((.*?)\n\)', text, re.S)
    require(tuple(re.findall(r'^  `([^`]+)`', header, re.M)) == TELE_COLUMNS,
            'Unexpected game_tele column order')
    require(text.count('INSERT INTO `game_tele` VALUES\n') == 1, 'Unexpected game_tele INSERT')
    result = []
    for line in text.splitlines():
        if not line.startswith('('):
            continue
        value = line.rstrip(',;')
        require(value.startswith('(') and value.endswith(')'), 'Malformed game_tele tuple')
        fields, = list(csv.reader([value[1:-1]], delimiter=',', quotechar="'", escapechar='\\',
                                  doublequote=False, strict=True))
        require(len(fields) == 7, 'Expected seven game_tele fields')
        require(re.fullmatch(r'\d+', fields[0]) and re.fullmatch(r'\d+', fields[5]), 'Invalid tele integer')
        row = dict(zip(TELE_COLUMNS, [int(fields[0]), *(float(v) for v in fields[1:5]),
                                      int(fields[5]), fields[6]]))
        require(0 < row['id'] <= 0xFFFFFFFF and 0 <= row['map'] <= 0xFFFF
                and all(math.isfinite(row[k]) for k in TELE_COLUMNS[1:5]) and bool(row['name']),
                'Invalid game_tele numeric/name value')
        result.append(row)
    require(len({r['id'] for r in result}) == len(result), 'Duplicate game_tele ID')
    return result


def destinations():
    rows = tele_rows(TELE_SQL.read_text())
    result = []
    for spawn in spawns():
        matches = [r for r in rows if all(r[k] == spawn[k] for k in TELE_COLUMNS[1:6])]
        require(len(matches) == 1, 'No unique exact game_tele spawn anchor')
        row, = matches
        require(re.fullmatch(r'[A-Za-z]+', row['name']), 'Pinned tele name must be one exact token')
        require(sum(r['name'].casefold() == row['name'].casefold() for r in rows) == 1,
                'Ambiguous selected game_tele name')
        result.append(row)
    return result


def control_anchor(spawn):
    return spawns()[CONTROL_ANCHORS[spawn['map']]]


def command_set(guid, spawn):
    require(guid in OWNERS and spawn in [spawns()[i] for i in CITIES[guid]], 'Unsafe teleport target/city')
    anchor = control_anchor(spawn)
    destination = destinations()[spawns().index(spawn)]
    return {'.go xyz ' + ' '.join(str(anchor['position_' + n]) for n in 'xyz') + ' ' + str(anchor['map']),
            '.tele name ' + OWNERS[guid][2] + ' ' + destination['name'], '.npc info ' + str(spawn['guid'])}


def at_point(client, point):
    return client.world is not None and client.world[0] == point['map'] and sum(
        (client.world[n + 1] - point['position_' + axis]) ** 2 for n, axis in enumerate('xyz')) <= 25


def loaded_merchant(gm, player, spawn, messages):
    require(gm.guid == 13 and player.guid in OWNERS
            and spawn in [spawns()[i] for i in CITIES[player.guid]] and at_point(gm, control_anchor(spawn))
            and at_point(player, spawn) and gm.world[0] == player.world[0] == spawn['map'],
            'Wrong control anchor/actor city/map')
    text = '\n'.join(messages)
    require(re.findall(r'DB GUID: (\d+),', text) == [str(spawn['guid'])], 'Wrong loaded spawn')
    native = transfer.observed_guid(messages, 'Creature', 900500)
    positions = re.findall(r'^Position: (\S+) (\S+) (\S+)\.$', text, re.M)
    require(len(positions) == 1, 'No unique native NPC position')
    coords = [float(v) for v in positions[0]]
    require(all(math.isfinite(v) for v in coords)
            and sum((coords[n] - spawn['position_' + axis]) ** 2 for n, axis in enumerate('xyz')) <= 25
            and sum((coords[n] - player.world[n + 1]) ** 2 for n in range(3)) <= 25,
            'Native NPC/actor outside five yards')
    require('AIName:  ScriptName: archipelago_merchant' in messages
            and 'SpellSchoolImmuneMask: 0' in messages, 'Incomplete native merchant info')
    return native


def release_guard(release, now=None):
    now = now or datetime.now(timezone.utc)
    issued, expires = (datetime.fromisoformat(release[k]) for k in ('issued_utc', 'expires_utc'))
    require(issued.tzinfo is not None and expires.tzinfo is not None and issued <= now < expires
            and 0 < (expires - issued).total_seconds() <= 1800, 'Fresh release, maximum 30 minutes')
    require(all(release.get(k) is True for k in ('owned_release', 'gui40_released', 'mail46_released',
            'native_matrix_released', 'all_native_owners_released', 'all_offline', 'no_other_runners'))
            and release.get('world_sha256') == transfer.WORLD_HASH and bool(release.get('release_id')),
            'Explicit parent release of all owners required')
    return release


def parent_release():
    return release_guard(json.loads((OUTPUT / 'release.json').read_text()))


def source_evidence():
    evidence = transfer.probe_source()
    require(evidence['base_manifest_sha256'] == '0edea8dba721f996f00cf0b5c95e3576fff1ad4dd6e637fd8c0ad45b06f1285b', 'Wrong base manifest')
    inventory = load('.local/city-merchants-plan/helper-hashes.json')
    require(all(artisan.digest(ROOT / p) == h for p, h in inventory.items()), 'Native/helper source changed')
    native = json.loads((artisan.BUILD / 'source-files.sha256.json').read_text())
    for path, digest in inventory.items():
        if path.startswith(str(artisan.SOURCE.relative_to(ROOT)) + '/'):
            require(native[str((ROOT / path).relative_to(artisan.SOURCE))] == digest, 'Helper differs from build inventory')
    review = load('.local/city-merchants-plan/exploration-source-review.json')
    require(all(artisan.digest(Path(p)) == h for p, h in review['files'].items()), 'Exploration source changed')
    config = (ROOT / '.local/v2-realm/config/worldserver.conf').read_text()
    require(re.findall(r'^Rate\.XP\.Explore\s*=\s*([^#\s]+)', config, re.M) == ['1'], 'Exploration rate must remain 1')
    evidence['exploration_review'] = review
    paths = ['data/sql/base/db_world/game_tele.sql', 'data/sql/base/db_world/acore_string.sql',
             'data/sql/base/db_auth/rbac_linked_permissions.sql', 'data/sql/base/db_auth/rbac_default_permissions.sql',
             'src/server/game/Accounts/RBAC.h', 'src/server/game/Miscellaneous/Language.h',
             'src/server/scripts/Commands/cs_tele.cpp', 'src/server/scripts/Commands/cs_npc.cpp',
             'src/server/game/Chat/Chat.cpp', 'src/server/game/Chat/ChatCommands/ChatCommandArgs.cpp',
             'src/server/game/Chat/ChatCommands/ChatCommand.cpp',
             'src/server/game/Globals/ObjectMgr.cpp', 'modules/mod-archipelago/src/APProgression.cpp']
    hashes = {p: artisan.digest(artisan.SOURCE / p) for p in paths}
    require(all(native[p] == h for p, h in hashes.items()), 'Map-control source differs from build inventory')
    require(control_positive_areas() == {1519: 10, 1657: 10, 4395: 75}, 'Control anchor ancestry changed')
    require('(6,55)' in XP_TABLE.read_text() and '(1,400)' in
            (artisan.SOURCE / 'data/sql/base/db_world/player_xp_for_level.sql').read_text(), 'Control XP bound changed')
    evidence['map_control'] = dict(hashes=hashes, destinations=destinations(),
                                   positive_areas=control_positive_areas(), maximum_saved_xp=220)
    return evidence


def control_positive_areas():
    dbc = DBC(artisan.DBC_DIR / 'AreaTable.dbc')
    result = {}
    for area, row in dbc.rows.items():
        root, seen = area, set()
        while root in dbc.rows and root not in seen and dbc.rows[root][2]:
            seen.add(root)
            root = dbc.rows[root][2]
        if root in {CITY_AREAS[i] for i in CONTROL_ANCHORS.values()} and 0 < row[10] < 0x80000000:
            result[area] = row[10]
    return result


def exploration_credit(guid, city, phase, session, payload):
    control = guid == 13
    require((control and city in CONTROL_ANCHORS.values()) or
            (guid in OWNERS and city in CITIES[guid]), 'Unexpected exploration actor/city')
    require(phase in ('login', 'teleport', 'menus', 'logout') and isinstance(session, int) and session > 0,
            'Outside city phase/session')
    require(len(payload) == 8, 'Exploration packet must be exactly eight bytes')
    area, amount = struct.unpack('<II', payload)
    dbc = DBC(artisan.DBC_DIR / 'AreaTable.dbc')
    row = dbc.rows.get(area)
    require(row is not None and 0 < row[10] < 0x80000000, 'Area cannot emit exploration XP')
    ancestor, seen = area, set()
    while ancestor in dbc.rows and ancestor not in seen and dbc.rows[ancestor][2]:
        seen.add(ancestor)
        ancestor = dbc.rows[ancestor][2]
    allowed = CONTROL_ANCHORS.values() if control and phase == 'login' else (city,)
    require(any(ancestor == CITY_AREAS[i] and row[1] == spawns()[i]['map'] for i in allowed),
            'Exploration outside current approved role ancestry')
    if control:
        require(control_positive_areas() == {1519: 10, 1657: 10, 4395: 75}
                and area in control_positive_areas(), 'Unexpected control exploration area')
    base = {int(k): int(v) for k, v in re.findall(r'\((\d+),(\d+)\)', XP_TABLE.read_text())}
    level, area_level = (1 if control else OWNERS[guid][5]), row[10]
    diff = level - area_level
    expected = base.get(level + 5 if diff < -5 else area_level, 0)
    if diff > 5:
        expected = expected * max(0, min(100, 100 - (diff - 5) * 5)) // 100
    require(amount == expected, 'Exploration XP differs from source table/formula at rate 1')
    return dict(actor=guid, city=city, phase=phase, session=session, areaId=area, amount=amount, raw=payload.hex())


def gossip_packet(data):
    require(len(data) >= 24, 'Truncated gossip header')
    npc, menu, title, count = struct.unpack_from('<QIII', data)
    require(count <= 32, 'Oversized gossip menu')
    offset, rows = 20, []
    for _ in range(count):
        require(offset + 10 <= len(data), 'Truncated gossip option')
        option, icon, coded, money = struct.unpack_from('<IBBI', data, offset)
        offset += 10
        strings = []
        for _ in range(2):
            end = data.find(b'\0', offset)
            require(end >= offset, 'Unterminated gossip text')
            strings.append(data[offset:end].decode('utf-8'))
            offset = end + 1
        require(not coded and money == 0, 'Unexpected coded/money option')
        rows.append(dict(option=option, text=strings[0], box=strings[1]))
    require(data[offset:] == b'\0\0\0\0' and len({r['option'] for r in rows}) == count,
            'Unexpected quests, trailing data, or duplicate options')
    return dict(npc=npc, menu=menu, rows=rows)


def navigation(menu, option):
    row, = [r for r in menu['rows'] if r['option'] == option]
    require(not row['box'] and (row['text'] in ('Weapons / shields / held items', 'Armor / cloaks',
            'Jewelry / trinkets', 'Set pieces', 'Next page') or 'Back to categories' in row['text']),
            'Only observed category/page navigation; never purchase')
    return struct.pack('<QII', menu['npc'], menu['menu'], option)


def menu_stock(menus, expected, balance):
    actual = []
    cost = sum(r['price'] for r in expected if not r['sold'])
    for menu in menus:
        require(menu['rows'][0]['text'] == f'Vouchers: {balance} | Remaining total cost: {cost}',
                'Packet balance/remaining cost differs')
        for row in menu['rows']:
            if not row['text'].startswith('#'):
                continue
            match = re.fullmatch(r'#(\d+) \|c[0-9a-f]+\|Hitem:(\d+):[^|]+\|h\[[^\]]+\]\|h\|r \| (\d+) vouchers \| (SOLD|Buy one)', row['text'])
            require(match is not None, 'Invalid stock label')
            index, entry, price, sold = match.groups()
            actual.append(dict(stock_index=int(index), item_entry=int(entry), price=int(price), sold=sold == 'SOLD'))
    keys = ('stock_index', 'item_entry', 'price', 'sold')
    require(sorted(actual, key=lambda r: r['stock_index']) == [{k: r[k] for k in keys} for r in expected],
            'Missing, duplicate, or mutated stock rows')
    return dict(stock=actual, vouchers=balance, remaining_cost=cost)


class CityClient(TravelClient):
    def __init__(self, sock, authorize, guid):
        self.guid, self.commands, self.menu = guid, set(), None
        self.city, self.phase, self.session = None, 'login', None
        self.exploration_credits = []
        self.allowed_selection = None
        self.route_guid, self.route_spawn = None, None
        self.ack, self.teleports = None, 0
        self.teleport_evidence = []
        super().__init__(sock, authorize)

    def send(self, opcode, payload=b''):
        if opcode == 0x95:
            require(self.guid == 13 and self.route_guid in OWNERS and self.route_spawn is not None
                    and payload in {say_packet(c) for c in self.commands & command_set(self.route_guid, self.route_spawn)},
                    'Unsafe GM command')
            require(payload == say_packet(next(c for c in command_set(self.route_guid, self.route_spawn)
                                                if c.startswith('.go ')))
                    or at_point(self, control_anchor(self.route_spawn)), 'Control not at approved map anchor')
        elif opcode == 0x17B:
            require(self.guid in OWNERS and self.allowed_selection is not None
                    and payload == struct.pack('<Q', self.allowed_selection), 'Unobserved merchant')
        elif opcode == 0x17C:
            require(self.guid in OWNERS and self.menu is not None and payload in
                    {navigation(self.menu, r['option']) for r in self.menu['rows']
                     if not r['box'] and (r['text'] in ('Weapons / shields / held items', 'Armor / cloaks',
                     'Jewelry / trinkets', 'Set pieces', 'Next page') or 'Back to categories' in r['text'])},
                    'Unsafe gossip select')
        elif opcode in (0xDC, 0xC7):
            require(self.ack == (opcode, payload), 'Unsolicited teleport ACK')
            self.ack = None
        else:
            require(opcode in (0x1ED, 0x37, 0x3D, 0x1DC, 0x391, 0x4B), 'Forbidden operation')
            if opcode == 0x3D:
                require(payload == struct.pack('<Q', self.guid), 'Wrong login target')
            if opcode in (0x37, 0x4B):
                require(not payload, 'Unexpected payload')
        super().send(opcode, payload)
        if opcode in (0xDC, 0xC7):
            transfer.emit('city_tp_ack', guid=self.guid, monotonic_ns=time.monotonic_ns(),
                          opcode=hex(opcode), sha256=transfer.digest(payload))

    def process(self, opcode, payload):
        if opcode == 0x1F8:
            credit = exploration_credit(self.guid, self.city, self.phase, self.session, payload)
            require(not any(c['actor'] == self.guid and c['areaId'] == credit['areaId']
                            for c in self.exploration_credits), 'Repeated exploration credit')
            self.exploration_credits.append(credit)
        if opcode == 0x3E:
            self.ack = (0xDC, b'')
        elif opcode == 0xC7:
            guid, offset = transfer.packed_guid(payload)
            require(guid == self.guid and len(payload) >= offset + 30, 'Wrong teleport mover')
            sequence, = struct.unpack_from('<I', payload, offset)
            self.ack = (0xC7, payload[:offset] + struct.pack('<II', sequence, 0))
        elif opcode == 0x17D:
            self.menu = gossip_packet(payload)
            require(self.menu['npc'] == self.allowed_selection, 'Foreign gossip reply')
        if opcode in (0x3E, 0xC7):
            transfer.emit('city_tp_packet', guid=self.guid, monotonic_ns=time.monotonic_ns(),
                          opcode=hex(opcode), sha256=transfer.digest(payload))
        super().process(opcode, payload)
        if opcode in (0x3E, 0xC7):
            require(self.ack is None, 'Teleport ACK not sent')
            self.teleports += 1
            self.teleport_evidence.append(dict(monotonic_ns=time.monotonic_ns(), world=self.world))
            transfer.emit('city_tp_destination', guid=self.guid, **self.teleport_evidence[-1])


class CityRunner(Runner):
    reuse_control = MerchantRunner.reuse_control

    def __init__(self, db, deadline):
        self.deadline = deadline
        self.exploration_credits, self.sessions = [], 0
        self.current_city = None
        super().__init__(db, 'APV2F')

    def query(self, sql, args=()):
        require(time.monotonic() < self.deadline + 65, 'Cleanup observation deadline')
        return super().query(sql, args)

    def offline(self, guid):
        end = min(time.monotonic() + 35, self.deadline + 60)
        while time.monotonic() < end:
            row = self.character(guid)
            if row is not None and row['online'] == 0:
                accounts = self.query('SELECT online FROM acore_auth.account WHERE id=%s', (row['account'],))
                if accounts == [dict(online=0)]:
                    return row
            time.sleep(.2)
        raise RuntimeError('Offline cleanup deadline; no SQL fallback')

    def bounded(self):
        require(time.monotonic() < self.deadline, '1800-second runtime limit')
        parent_release()

    def ownership(self):
        inventory = load('.local/city-merchants-plan/ownership-hashes.json')
        require(len(inventory) >= 12 and all(artisan.digest(ROOT / p) == h for p, h in inventory.items()), 'Ownership evidence changed')
        require(load('.local/travel-live/summary.json')['result']['event'] == 'PASS', 'Travel birth proof failed')
        require(load('.local/class-matrix-plan/parent-reviewed-seven.json')['protected_final_exactly_equals_before'] is True,
                'Parent seven-class review missing')
        runroot = str(Path(CASE7).parent) + '/'
        require(load(runroot + 'before.json') == load(runroot + 'final-protected-snapshot.json'),
                'Original matrix protected snapshot mismatch')
        results = load(runroot + 'summary.json')['classes']
        require(any(r.get('class_id') == 7 and r.get('guid') == 37 and r.get('status') == 'PASS native fixture gates'
                    for r in results), 'Case 7 individual replay PASS missing; root FAIL must remain')
        for guid, (account, account_id, name, race, cls, level, binding) in OWNERS.items():
            prefix = '.local/travel-live/' if guid == 24 else CASE7
            creation = load(prefix + 'creation.json')
            require(all(creation.get(k) == v for k, v in dict(guid=guid, account=account, name=name).items()), 'No trusted birth')
            manifest = load(prefix + 'manifest.json')
            proof = load('.local/travel-extension/final-observations.json' if guid == 24 else CASE7 + 'replay.json')
            if guid == 37:
                require(load(CASE7 + 'first-login-authorized.json')['profile'] == manifest['profile'], 'First login profile mismatch')
            row = self.account_row(account)
            guard_account(row, account)
            require(row['id'] == account_id, 'Owner account changed')
            private = self.query('SELECT email,reg_mail,salt,verifier FROM acore_auth.account WHERE id=%s', (account_id,))
            require(len(private) == 1, 'Missing private credential markers')
            check_account(private[0], account, 'test-only')
            character = self.character(guid)
            require(all(character.get(k) == v for k, v in dict(guid=guid, account=account_id, name=name,
                    race=race, **{'class': cls}, level=level, online=0).items()), 'Owned profile changed')
            stored = self.query('SELECT * FROM acore_characters.mod_archipelago_binding WHERE character_guid=%s', (guid,))
            require(len(stored) == 1 and stored[0]['id'] == binding, 'Binding changed')
            require(immutable_binding(stored[0]) == immutable_binding(proof['binding'][0])
                    and json.loads(stored[0]['manifest']) == manifest
                    and transfer.digest(canonical(manifest).encode()) == stored[0]['manifest_hash'], 'Manifest/seed/checksum changed')
            receipts = self.query('SELECT * FROM acore_characters.mod_archipelago_reward WHERE binding_id=%s ORDER BY item_index', (binding,))
            require(json.loads(json.dumps(receipts, default=str)) == proof.get('receipts', proof.get('rewards')),
                    'Current stored receipt prefix changed')
            progress = self.query('SELECT * FROM acore_characters.mod_archipelago_progress WHERE binding_id=%s', (binding,))
            require(progress == proof['progress'] and len(manifest['merchant']['stock']) == 30, 'Progress or original 30 stock changed')
            require(manifest['profile']['race_id'] == race and manifest['profile']['class_id'] == cls
                    and manifest['seed_name'] == stored[0]['seed_name'], 'Birth manifest profile/seed mismatch')
            if guid == 37:
                fresh = load(CASE7 + 'fresh-offline.json')['character']
                require(fresh['guid'] == guid and fresh['name'] == name and fresh['account'] == account_id
                        and fresh['race'] == race and fresh['class'] == cls and fresh['level'] == 1
                        and fresh['online'] == 0, 'No original fresh level-1 birth proof')
                require(proof['receipts'] == load(CASE7 + 'relog.json')['receipts'], 'Individual replay receipt mismatch')
            self.known.add(guid)
            self.names[guid] = name
        self.reuse_control()
        control = self.character(13)
        require(control['xp'] == 55 and control['playerFlags'] in (0, 0x20)
                and control['extra_flags'] == 0, 'Control XP55/GM-off baseline changed')

    @contextmanager
    def login_owned(self, guid):
        self.bounded()
        require(guid in self.known and guid in (13, 24, 37), 'Not proved owned')
        account, account_id, name, race, cls = ('TEST', 1, self.names[13], 1, 1) if guid == 13 else OWNERS[guid][:5]
        from realm_client import authenticate
        profile = dict(race_id=race, class_id=cls)
        guard_account(self.account_row(account), account, setup=guid == 13)
        def authorize(candidate, events):
            require(candidate == guid and not any(e.startswith('CREATED ') for e in events), 'No creation permitted')
            guard_character(self.character(guid), account_id, name, self.known, expected_profile=profile)
        authorize(guid, [])
        client = None
        try:
            auth = authenticate(account, 'TEST' if guid == 13 else 'test-only', ready_timeout=30)
            realm = next((r for r in auth.realms if not r.locked and not r.flags & 3), None)
            require(realm is not None, 'No ready realm')
            with socket.create_connection(('127.0.0.1', 8085), timeout=10) as sock:
                client = CityClient(sock, authorize, guid)
                self.sessions += 1
                client.city = (CONTROL_ANCHORS[spawns()[self.current_city]['map']]
                               if guid == 13 else self.current_city)
                client.session = self.sessions
                client.exploration_credits = self.exploration_credits
                try:
                    require(client.connect(account, auth, realm, name, race=race, class_id=cls).guid == guid, 'Wrong login')
                    client.stay(.5)
                    yield client
                finally:
                    if client.login:
                        client.phase = 'logout'
                        client.logout()
        finally:
            self.offline(guid)

    def frozen(self):
        bindings = {r['id'] for r in self.query('SELECT id FROM acore_characters.mod_archipelago_binding')}
        result = protected_snapshot(self, self.before, bindings)
        result['characters'] = [character_projection(r)
                               for r in self.query('SELECT * FROM acore_characters.characters ORDER BY guid')]
        for table in ('session', 'item', 'delivery'):
            result['legacy_' + table] = sorted(self.query('SELECT * FROM acore_characters.mod_archipelago_' + table), key=str)
        return result

    def compare(self, before):
        after = self.frozen()
        credits = getattr(self, 'exploration_credits', [])
        for credit in credits:
            require(exploration_credit(credit['actor'], credit['city'], credit['phase'], credit['session'],
                                      bytes.fromhex(credit['raw'])) == credit, 'Invalid exploration evidence')
        require(len({(c['actor'], c['areaId']) for c in credits}) == len(credits), 'Duplicate exploration evidence')
        for row in after.get('characters', []):
            if row['guid'] in (13, 24, 37):
                original, = [r for r in before['characters'] if r['guid'] == row['guid']]
                # Login's offline rest bonus can cross the core's >10 rested threshold.
                if row.get('restState') != original.get('restState'):
                    bonus, = self.query('SELECT rest_bonus FROM acore_characters.characters WHERE guid=%s', (row['guid'],))
                    require(original.get('restState') == 2 and row.get('restState') == 1
                            and bonus['rest_bonus'] > 10, 'Unproved rested-state change')
                    row['restState'] = original['restState']
                total = sum(c['amount'] for c in credits if c['actor'] == row['guid'])
                if row['guid'] == 13:
                    require(original['level'] == 1 and original['xp'] == 55 and len(
                        [c for c in credits if c['actor'] == 13]) <= 3 and total <= 165 and row['xp'] <= 220,
                        'Control level-1 XP bound')
                require(row['level'] == original['level'] and row['xp'] == original['xp'] + total,
                        'Owned level/XP delta differs from native exploration credits')
                row['xp'] = original['xp']
        old = before['ap_check']
        added = [r for r in after['ap_check'] if r not in old]
        for row in added:
            guid, = [g for g, o in OWNERS.items() if o[6] == row['binding_id']]
            prefix = '.local/travel-live/' if guid == 24 else CASE7
            allowed = {c['ap_id'] for c in load(prefix + 'manifest.json')['selected_checks'] if c['kind'] == 'exploration'}
            require(row['location_id'] in allowed and not row['acknowledged'], 'Only native owned exploration outbox additions')
        after['ap_check'] = [r for r in after['ap_check'] if r not in added]
        removed = [r for r in before['character_aura'] if r not in after['character_aura']]
        require(all(r['guid'] == 24 and r['spell'] == 32242 for r in removed), 'Unexpected aura removal')
        after['character_aura'] = sorted(after['character_aura'] + removed, key=lambda r: str(sorted(r.items())))
        require(after == before, 'Protected state or owned economics/items/skills/spells/talents changed')
        return added

    def menus(self, player):
        def request(opcode, payload):
            self.bounded()
            player.send(opcode, payload)
            player.menu = None
            end = time.monotonic() + 5
            while player.menu is None and time.monotonic() < end:
                player.stay(.1)
            require(player.menu is not None, 'No fresh native gossip reply')
            return player.menu
        home = request(0x17B, struct.pack('<Q', player.allowed_selection))
        pages = [home]
        categories = [r['option'] for r in home['rows'][1:5]]
        require(len(categories) == 4, 'Missing categories')
        for option in categories:
            home = request(0x17B, struct.pack('<Q', player.allowed_selection))
            page = request(0x17C, navigation(home, option))
            for _ in range(10):
                pages.append(page)
                more = [r for r in page['rows'] if r['text'] == 'Next page']
                if not more:
                    break
                page = request(0x17C, navigation(page, more[0]['option']))
            else:
                raise RuntimeError('Unbounded gossip paging')
        return pages

    def complete_transport(self, gm, player, spawn, command):
        require(gm.guid == 13 and player.guid in OWNERS
                and command in command_set(player.guid, spawn)
                and command.startswith(('.go ', '.tele name ')), 'Unsafe transport command')
        target = gm if command.startswith('.go ') else player
        point = control_anchor(spawn) if target is gm else spawn
        previous, start = len(target.teleport_evidence), len(gm.messages)
        sent = time.monotonic_ns()
        end = min(self.deadline, time.monotonic() + 15)
        name = OWNERS[player.guid][2]
        destination = destinations()[spawns().index(spawn)]['name']
        success = f'You are teleporting |cffffffff|Hplayer:{name}|h[{name}]|h|r to {destination}.'
        self.bounded()
        transfer.emit('city_command', guid=gm.guid, target=target.guid, command=command, monotonic_ns=sent)
        try:
            gm.send(0x95, say_packet(command))
            while True:
                self.bounded()
                require(time.monotonic() < end, 'Command completion deadline')
                for client in (gm, player):
                    self.bounded()
                    client.stay(min(.05, max(0, end - time.monotonic())))
                self.bounded()
                require(time.monotonic() < end, 'Command completion deadline')
                messages = gm.messages[start:]
                require(all(target is player and m == success for m in messages) and len(messages) <= 1,
                        'Native command refusal: ' + repr(messages))
                fresh = target.teleport_evidence[previous:]
                located = bool(fresh) and all(e['monotonic_ns'] >= sent for e in fresh) and target.world is not None
                if located:
                    located = at_point(target, point)
                if located and (target is gm or messages == [success]):
                    transfer.emit('city_command_complete', guid=gm.guid, target=target.guid,
                                  command=command, monotonic_ns=time.monotonic_ns())
                    return
        except BaseException as exc:
            transfer.emit('city_command_unresolved', guid=gm.guid, target=target.guid, command=command,
                          monotonic_ns=time.monotonic_ns(), error=str(exc), messages=gm.messages[start:])
            raise

    def merchant_info(self, gm, player, spawn):
        require(at_point(gm, control_anchor(spawn)) and at_point(player, spawn), 'Wrong query map/position')
        command = '.npc info ' + str(spawn['guid'])
        start = len(gm.messages)
        end = min(self.deadline, time.monotonic() + 15)
        try:
            self.bounded()
            gm.send(0x95, say_packet(command))
            while time.monotonic() < end:
                for client in (gm, player):
                    self.bounded()
                    client.stay(min(.05, max(0, end - time.monotonic())))
                self.bounded()
                messages = gm.messages[start:]
                require(not any('Not in world' in m for m in messages), 'DB fallback is not loaded NPC proof')
                if 'SpellSchoolImmuneMask: 0' in messages:
                    return loaded_merchant(gm, player, spawn, messages)
                require(not any('not found' in m.lower() or 'no such' in m.lower() for m in messages),
                        'Native NPC query refusal')
            raise RuntimeError('Native NPC query completion deadline')
        except BaseException as exc:
            transfer.emit('city_command_unresolved', guid=gm.guid, command=command,
                          monotonic_ns=time.monotonic_ns(), error=str(exc), messages=gm.messages[start:])
            raise

    def execute(self, before):
        observations = []
        # Future read-only preflight; offline preparation never connects to SQL.
        for tele in destinations():
            rows = self.query('SELECT id,position_x,position_y,position_z,orientation,map,name FROM acore_world.game_tele WHERE id=%s OR name=%s', (tele['id'], tele['name']))
            require(rows == [tele], 'Live game_tele full tuple differs from pinned source')
        for guid, indices in CITIES.items():
            stock = sorted((r for r in before['ap_stock'] if r['binding_id'] == OWNERS[guid][6]), key=lambda r: r['stock_index'])
            manifest = load(('.local/travel-live/' if guid == 24 else CASE7) + 'manifest.json')
            require([dict(wow_id=r['item_entry'], price=r['price'], max_purchases=1) for r in stock] == manifest['merchant']['stock']
                    and [r['stock_index'] for r in stock] == list(range(30)),
                    'Stored stock differs from immutable manifest')
            balance, = [r['vouchers'] for r in before['ap_progress'] if r['binding_id'] == OWNERS[guid][6]]
            baseline = None
            for index in indices:
                spawn = spawns()[index]
                rows = self.query('SELECT guid,id,map,position_x,position_y,position_z,orientation FROM acore_world.creature WHERE guid=%s', (spawn['guid'],))
                require(len(rows) == 1 and all(rows[0][k] == v for k, v in spawn.items() if k != 'city'), 'Live spawn differs from source')
                self.current_city = index
                with self.login_owned(13) as gm, self.login_owned(guid) as player:
                    gm.phase = player.phase = 'teleport'
                    gm.route_guid, gm.route_spawn = guid, spawn
                    gm.commands = command_set(guid, spawn)
                    commands = sorted(gm.commands)
                    for command in [c for c in commands if c.startswith('.go ')] + [c for c in commands if c.startswith('.tele name ')]:
                        self.complete_transport(gm, player, spawn, command)
                    player.allowed_selection = self.merchant_info(gm, player, spawn)
                    gm.phase = player.phase = 'menus'
                    pages = self.menus(player)
                    observed = menu_stock(pages, stock, balance)
                    require(baseline is None or observed == baseline, 'Personal stock differs between cities')
                    baseline = observed
                    observations.append(dict(guid=guid, city=spawn['city'], native_guid=player.allowed_selection, menus=pages, **observed))
                self.compare(before)
                save('observations.json', observations)
            with self.login_owned(guid):
                pass
            self.compare(before)
        return observations


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(dict(PLAN, spawns=spawns(), destinations=destinations(),
                              control_anchors=CONTROL_ANCHORS), indent=2))
        return 0
    parent_release()  # Never author a release here, including during preparation.
    evidence = source_evidence()
    require(os.environ.get('WOWPILAGO_DB_PASSWORD') == os.environ.get('WOWPILAGO_TEST_ACCOUNT_PASSWORD') == 'test-only', 'Private credentials required')
    with (OUTPUT / 'attempt.json').open('x') as handle:
        json.dump(dict(plan=PLAN, evidence=evidence, release=parent_release()), handle, indent=2)
    result = dict(status='FAIL', live_observations=0)
    runner = before = None
    try:
        # No global guard/client monkeypatch. The common Human Warrior snapshot stays unchanged.
        info = json.loads(artisan.docker('inspect', 'wow-test-worldserver-1'))[0]
        labels = info['Config']['Labels']
        require(info['State']['Running'] and info['Image'] == artisan.IMAGE
                and labels.get('com.docker.compose.project') == 'wow-test'
                and labels.get('com.docker.compose.service') == 'worldserver', 'Wrong live image/project')
        require(any(m['Destination'] == '/work/install' and not m['RW'] and Path(m['Source']).resolve() == (artisan.BUILD / 'install').resolve() for m in info['Mounts']), 'Wrong install mount')
        require(all(artisan.docker('exec', 'wow-test-worldserver-1', 'sha256sum', p).split()[0] == transfer.WORLD_HASH
                    for p in ('/proc/1/exe', '/work/install/bin/worldserver')), 'Wrong live binary')
        import pymysql
        with (OUTPUT / 'run.jsonl').open('x', buffering=1) as log, redirect_stdout(log), pymysql.connect(
                host='127.0.0.1', port=13317, user='root', password='test-only', autocommit=True,
                cursorclass=pymysql.cursors.DictCursor, connect_timeout=5, read_timeout=5, write_timeout=5) as db:
            runner = CityRunner(db, time.monotonic() + 1720)
            require(runner.query('SELECT @@server_uuid AS uuid') == [dict(uuid=UUID)], 'Wrong private database')
            require(not runner.query('SELECT guid FROM acore_characters.characters WHERE online<>0') and
                    not runner.query('SELECT id FROM acore_auth.account WHERE online<>0'), 'All characters/accounts must be offline')
            runner.ownership()
            before = runner.frozen()
            save('before.json', before)
            try:
                observations = runner.execute(before)
                result = dict(status='PASS native 30/actor, ten cities', live_observations=len(observations), gui_proof=False)
            finally:
                for guid in sorted(runner.known):
                    runner.offline(guid)
                save('after.json', runner.frozen())
                save('allowed-exploration.json', runner.compare(before))
    except Exception as exc:
        result = dict(status='FAIL', error=str(exc), gui_proof=False)
    finally:
        if runner is not None:
            save('native-exploration-credits.json', runner.exploration_credits)
        save('summary.json', result)
    return 0 if result['status'].startswith('PASS') else 1


if __name__ == '__main__':
    sys.exit(main())
