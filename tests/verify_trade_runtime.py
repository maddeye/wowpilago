"""Owned 22/23 only: native slot-0 offers, never acceptance or transfer."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time

from verify_runtime import Runner, SmokeClient, guard_account, guard_character, require
from verify_merchant_runtime import SOURCE, WORLD_HASH, FUNDS_RUN, FUNDS_HASH

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = {22: ('APV2D', 5, 'Apsqlkruenob', 12),
            23: ('APV2E', 6, 'Apsgiylwpuwg', 13)}
PLAN = {'network_without_run': False, 'fixtures': [22, 23],
        'checks': ['positive equipped and backpack unbound offers',
                   'AP Thunderfury 269 and purchased pick 285 refused in slot 0',
                   'cancel only; full logout; unchanged items and AP economics'],
        'excluded': ['accept/complete trade', 'mail', 'auction house', 'real AP ingress']}
LOG = None


def emit(event, **values):
    line = json.dumps(dict(event=event, **values), default=str, sort_keys=True)
    print(line, flush=True)
    if LOG:
        LOG.write(line + '\n')
        LOG.flush()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def ownership(data, summary):
    require(digest(data) == FUNDS_HASH, 'Prior run hash mismatch')
    events = [json.loads(line) for line in data.splitlines() if line.strip()]
    passes = [e for e in events if e.get('event') == 'PASS']
    require(len(passes) == 1 and summary.get('result') == passes[0]
            and summary.get('run_sha256') == FUNDS_HASH, 'Prior PASS/summary mismatch')
    require(all(passes[0].get(k) == v for k, v in dict(primary=22, peer=23, binding=12,
            peer_binding=13, authorized_thunderfury=269, purchased=285).items()), 'Prior fixture mismatch')
    seeds = {}
    for guid, (account, _, name, binding) in FIXTURES.items():
        require(guid in summary.get('offline_fixture_guids', []), 'Prior fixture not released')
        creations = [e for e in events if e.get('event') == 'login' and e.get('fresh')
                     and (e.get('guid') == guid or e.get('name') == name)]
        require(creations == [dict(event='login', account=account, fresh=True, guid=guid, name=name)],
                'No unique trusted creation')
        ingress = [e for e in events if e.get('event') == 'fabricated_ingress' and e.get('guid') == guid]
        require(len(ingress) == 1 and ingress[0]['account'] == account
                and ingress[0]['binding'] == binding, 'Prior binding mismatch')
        seeds[guid] = ingress[0]['seed']
    return seeds


def trade_status(payload):
    require(len(payload) >= 4, 'Truncated trade status')
    status, = struct.unpack_from('<I', payload)
    sizes = {1: 12, 2: 8, 12: 13, 22: 5, 23: 5}
    require(status in set(range(13)) | set(range(14, 24))
            and len(payload) == sizes.get(status, 4), 'Invalid trade status layout')
    result = {'status': status}
    if status == 1:
        result['trader'], = struct.unpack_from('<Q', payload, 4)
    elif status == 12:
        result['inventory_result'], result['target'], result['limit'] = struct.unpack_from('<IBI', payload, 4)
    elif status in (22, 23):
        result['slot'] = payload[4]
    return result


def trade_extended(payload):
    # Native SendUpdateTrade: 21-byte header, seven fixed 73-byte slots.
    require(len(payload) == 21 + 7 * 73, 'Invalid extended trade size')
    view, trade_id, count, count2, money, spell = struct.unpack_from('<BIIIII', payload)
    require(view in (0, 1) and trade_id == 0 and count == count2 == 7, 'Invalid trade header')
    slots = []
    for slot in range(7):
        offset = 21 + slot * 73
        require(payload[offset] == slot, 'Invalid trade slot order')
        entry, display, count, wrapped = struct.unpack_from('<IIII', payload, offset + 1)
        slots.append(dict(slot=slot, entry=entry, display=display, count=count, wrapped=wrapped))
    return dict(view=view, money=money, spell=spell, slots=slots)


def offer_packet(bag, slot):
    require(type(bag) is int and bag == 0 and type(slot) is int and 0 <= slot < 39,
            'Only observed own equipment/backpack allowed')
    return struct.pack('<BBB', 0, 255, slot)


def allowed_send(opcode, payload, guid):
    require(guid in FIXTURES, 'Protected session')
    allowed = {0x1ED, 0x37, 0x3D, 0x1DC, 0x391, 0x4B, 0x116, 0x117, 0x11C, 0x11D}
    require(opcode in allowed, 'Forbidden opcode, including creation/acceptance/commands')
    if opcode == 0x3D:
        require(payload == struct.pack('<Q', guid), 'Wrong login GUID')
    elif opcode == 0x116:
        require(payload == struct.pack('<Q', 23 if guid == 22 else 22), 'Wrong trade target')
    elif opcode == 0x11D:
        require(len(payload) == 3 and payload[0] == 0 and payload[1] == 255
                and payload[2] < 39, 'Only tradable slot 0 allowed')
    elif opcode in (0x37, 0x117, 0x11C, 0x4B):
        require(not payload, 'Unexpected opcode payload')


class TradeClient(SmokeClient):
    def __init__(self, sock, authorize, guid):
        self.guid = guid
        self.statuses, self.updates, self.errors = [], [], []
        super().__init__(sock, authorize)

    def send(self, opcode, payload=b''):
        allowed_send(opcode, payload, self.guid)
        emit('packet', guid=self.guid, direction='CMSG', opcode=hex(opcode), raw=payload.hex())
        super().send(opcode, payload)

    def receive(self):
        opcode, payload = super().receive()
        emit('packet', guid=self.guid, direction='SMSG', opcode=hex(opcode), raw=payload.hex())
        return opcode, payload

    def process(self, opcode, payload):
        if opcode == 0x120:
            result = trade_status(payload)
            self.statuses.append(result)
            emit('trade_status', guid=self.guid, **result)
            require(result['status'] not in (4, 8), 'Unexpected acceptance/completion')
        elif opcode == 0x121:
            result = trade_extended(payload)
            self.updates.append(result)
            emit('trade_update', guid=self.guid, **result)
        elif opcode == 0x112:
            require(bool(payload), 'Empty inventory error')
            self.errors.append(payload[0])
            emit('inventory_error', guid=self.guid, code=payload[0])
        super().process(opcode, payload)


def probe_source():
    names = ['src/server/game/Handlers/TradeHandler.cpp',
             'src/server/game/Entities/Item/Item.cpp',
             'src/server/game/Entities/Player/PlayerStorage.cpp',
             'src/server/game/Entities/Player/Player.h',
             'src/server/game/Entities/Player/TradeData.h',
             'src/server/game/Entities/Player/TradeData.cpp',
             'src/server/shared/SharedDefines.h',
             'src/server/game/Handlers/ChatHandler.cpp',
             'src/server/game/Server/Protocol/Opcodes.h']
    hashes = {name: digest((SOURCE / name).read_bytes()) for name in names}
    require('#define INVENTORY_SLOT_BAG_0    255' in (SOURCE / names[3]).read_text(), 'Backpack mapping changed')
    for path in sorted((ROOT / 'src').glob('*')):
        if path.suffix in ('.h', '.cpp'):
            data = path.read_bytes()
            require(data == (SOURCE / 'modules/mod-archipelago/src' / path.name).read_bytes(),
                    'Module differs: ' + path.name)
            hashes['module/' + path.name] = digest(data)
    binary = subprocess.check_output(['docker', 'exec', 'wow-test-worldserver-1', 'sha256sum', '/proc/1/exe'],
                                     text=True, timeout=10).split()[0]
    require(binary == WORLD_HASH, 'World binary changed')
    return dict(hashes=hashes, world=binary)


class TradeRunner(Runner):
    def __init__(self, db):
        super().__init__(db, 'APV2D')

    def reuse(self):
        data = FUNDS_RUN.read_bytes()
        summary_data = (FUNDS_RUN.parent.parent / 'summary.json').read_bytes()
        seeds = ownership(data, json.loads(summary_data))
        for guid, (account, account_id, name, binding) in FIXTURES.items():
            row = self.account_row(account)
            guard_account(row, account)
            require(row['id'] == account_id, 'Account ID changed')
            row = self.character(guid)
            require(row and all(row.get(k) == v for k, v in dict(guid=guid, account=account_id,
                    name=name, race=1, **{'class': 1}, level=1, online=0).items()), 'Owned profile changed')
            rows = self.query('SELECT id,character_guid,character_name,character_account,seed_name,class_id,race_id '
                              'FROM acore_characters.mod_archipelago_binding WHERE character_guid=%s', (guid,))
            require(rows == [dict(id=binding, character_guid=guid, character_name=name,
                    character_account=account_id, seed_name=seeds[guid], class_id=1, race_id=1)], 'Binding changed')
        for guid, (_, _, name, _) in FIXTURES.items():
            self.known.add(guid)
            self.names[guid] = name
        emit('verified_owned_reuse', guids=[22, 23], run_sha256=FUNDS_HASH,
             summary_sha256=digest(summary_data))

    @contextmanager
    def login(self, guid):
        from realm_client import authenticate
        require(guid in self.known and guid in FIXTURES, 'Unverified login')
        account, account_id, name, _ = FIXTURES[guid]
        guard_account(self.account_row(account), account)
        guard_character(self.character(guid), account_id, name, self.known)
        require(self.character(guid)['online'] == 0, 'Fixture busy')

        def authorize(candidate, events):
            require(candidate == guid and not any(e.startswith('CREATED ') for e in events), 'Not existing owned fixture')
            guard_character(self.character(candidate), account_id, name, self.known)
        auth = authenticate(account, os.environ['WOWPILAGO_TEST_ACCOUNT_PASSWORD'])
        realm = next((r for r in auth.realms if not r.locked and not r.flags & 3), None)
        require(realm is not None, 'No ready realm')
        with socket.create_connection(('127.0.0.1', 8085), timeout=10) as sock:
            client = TradeClient(sock, authorize, guid)
            try:
                chosen = client.connect(account, auth, realm, name, race=1, class_id=1)
                require(chosen.guid == guid, 'Wrong fixture')
                client.stay(.5)
                yield client
            finally:
                if client.login:
                    try:
                        client.send(0x11C)
                    finally:
                        client.logout()
                        emit('normal_logout', guid=guid)
        self.offline(guid)

    def saved(self):
        snapshots = {}
        for guid, (account, _, _, binding) in FIXTURES.items():
            self.account = account
            snapshots[str(guid)] = self.snapshot(guid, binding)
            snapshots[str(guid)]['bindings'] = self.query(
                'SELECT * FROM acore_characters.mod_archipelago_binding WHERE character_guid=%s', (guid,))
            snapshots[str(guid)]['account'] = self.account_row(account)
        return dict(fixtures=snapshots,
                    protected=self.query('SELECT * FROM acore_characters.characters WHERE guid IN (1,2,3,4) ORDER BY guid'),
                    population=self.query('SELECT guid,name,account FROM acore_characters.characters ORDER BY guid'))

    def prepare(self, before):
        primary = before['fixtures']['22']
        peer = before['fixtures']['23']
        for snap in (primary, peer):
            require(snap['progress'][0]['vouchers'] == 4, 'Expected four vouchers')
        for snap, guid, owner, entry, slot in ((primary, 269, 22, 19019, 15),
                                               (primary, 285, 22, 756, 38),
                                               (peer, 270, 23, 19019, 24),
                                               (peer, 286, 23, 756, 25)):
            item = next((i for i in snap['items'] if i['guid'] == guid), None)
            require(item and item['owner_guid'] == owner and item['itemEntry'] == entry
                    and item['flags'] == 1, 'Expected bound fixture item')
            require(dict(bag=0, slot=slot, item=guid) in snap['inventory'], 'Expected item placement')
        require({269, 285} <= {r['item_guid'] for r in primary['authorized']}, 'Missing AP authorization')
        require(270 not in {r['item_guid'] for r in peer['authorized']}, 'Ordinary peer sword became AP')
        controls = []
        for guid, entry, slot in ((250, 38, 3), (256, 49778, 24)):
            item = next(i for i in primary['items'] if i['guid'] == guid)
            require(item['flags'] == 0 and item['owner_guid'] == 22 and item['itemEntry'] == entry
                    and dict(bag=0, slot=slot, item=guid) in primary['inventory'], 'Positive control changed')
            template = self.query('SELECT entry,name,bonding,RequiredLevel,InventoryType FROM acore_world.item_template WHERE entry=%s', (entry,))
            require(len(template) == 1 and template[0]['bonding'] == 0, 'Control not unbound')
            controls.append(dict(guid=guid, entry=entry, slot=slot, template=template[0]))
        templates = self.query('SELECT entry,name,bonding,RequiredLevel,InventoryType FROM acore_world.item_template WHERE entry IN (19019,756) ORDER BY entry')
        emit('validated_items', controls=controls, ap_templates=templates)
        return controls

    def attempt(self, a, b, control, ap_guid, ap_slot):
        def pump():
            a.stay(.3)
            b.stay(.3)
        a.statuses.clear()
        b.statuses.clear()
        a.send(0x116, struct.pack('<Q', 23))
        pump()
        require(b.statuses == [dict(status=1, trader=22)], 'No actual target handshake')
        b.send(0x117)
        pump()
        require(a.statuses == [dict(status=2)] and b.statuses[-1] == dict(status=2), 'Trade window not open')
        a.updates.clear()
        b.updates.clear()
        a.send(0x11D, offer_packet(0, control['slot']))
        pump()
        require(dict(status=7) in a.statuses, 'Owner did not return to trade')
        require(any(u['view'] == 1 and u['slots'][0]['entry'] == control['entry']
                    and u['slots'][0]['count'] == 1 and u['money'] == u['spell'] == 0
                    for u in b.updates), 'Unbound control not offered in actual peer view')
        a.statuses.clear()
        a.updates.clear()
        b.updates.clear()
        a.send(0x11D, offer_packet(0, ap_slot))
        pump()
        require(a.statuses == [dict(status=3)], 'Expected native CanBeTraded cancellation, not generic failure')
        require(not a.updates and not b.updates and not a.errors and not b.errors,
                'AP offer changed trade data or returned confounding inventory error')
        emit('ap_offer_refused', guid=ap_guid, slot=0, inventory_slot=ap_slot,
             positive_control=control, native_status=3, control_remains_in_offer=True)
        a.statuses.clear()
        b.statuses.clear()
        a.send(0x11C)
        pump()
        require(dict(status=3) in a.statuses and dict(status=3) in b.statuses, 'Cancel not seen on both sessions')
        emit('cancelled_without_accept', item=ap_guid)


def save(path, data):
    path.write_text(json.dumps(data, indent=2, default=str) + '\n')


def main(argv=None):
    global LOG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(PLAN, indent=2))
        return 0
    require(os.environ.get('WOWPILAGO_TEST_ACCOUNT_PASSWORD') == 'test-only'
            and os.environ.get('WOWPILAGO_DB_PASSWORD') == 'test-only', 'Explicit test-only credentials required')
    output = ROOT / '.local/trade-live' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    output.mkdir(parents=True)
    import pymysql
    with (output / 'run.jsonl').open('x') as log:
        LOG = log
        result = dict(event='FAIL', error='Not completed')
        before = None
        runner = None
        try:
            emit('pinned_source', **probe_source())
            with pymysql.connect(host='127.0.0.1', port=13317, user='root', password='test-only',
                                 autocommit=True, cursorclass=pymysql.cursors.DictCursor,
                                 connect_timeout=5, read_timeout=15, write_timeout=15) as db:
                runner = TradeRunner(db)
                runner.reuse()
                before = runner.saved()
                save(output / 'before.json', before)
                emit('before_select', snapshot=before)
                try:
                    controls = runner.prepare(before)
                    with runner.login(22) as a, runner.login(23) as b:
                        runner.attempt(a, b, controls[0], 269, 15)
                        runner.attempt(a, b, controls[1], 285, 38)
                finally:
                    for guid in runner.known:
                        runner.offline(guid)
                    after = runner.saved()
                    save(output / 'after.json', after)
                    emit('after_select', snapshot=after)
                    require(before == after, 'Inventory/ownership/markers/economics changed after logout')
                emit('final_source', **probe_source())
                result = dict(event='PASS', checks=PLAN['checks'], offline_fixture_guids=[22, 23],
                              unchanged=True, no_accept_or_transfer=True, remaining=PLAN['excluded'])
        except Exception as exc:
            result = dict(event='FAIL', error=str(exc), history='Preserved; no repair/reset or fallback')
        emit(**result)
        save(output / 'summary.json', dict(result=result, run_sha256=digest((output / 'run.jsonl').read_bytes()),
                                         prior_run_sha256=FUNDS_HASH, output=str(output)))
        LOG = None
    return 0 if result['event'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
