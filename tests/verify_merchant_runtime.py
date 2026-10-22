"""Bounded native merchant checks using fabricated AP ingress, not a real AP room.

No arguments prints an offline plan. Runtime preserves every fixture and receipt.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import struct
import subprocess
import sys
import time

from verify_runtime import Runner, guard_account, require, manifest_fixture, selection_packet, LABEL
from bridge.catalog import Catalog

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.local/v2-build/20261019T150600.624050Z/source'
ACCOUNTS = ('APV2D', 'APV2E', 'APV2F')
CONTROL_EVIDENCE = ROOT / '.local/class-systems'
CONTROL_GUID, CONTROL_NAME = 13, 'Apsjxsocfsik'
FUNDS_RUN = ROOT / '.local/merchant-live/20261019T174525Z/run.jsonl'
FUNDS_HASH = '701eaa733913ac95ca1a36bbb2573e794d24c13202bf7a640dabe92a2527c98d'
FUNDS_NAME = 'Apsgiylwpuwg'
FUNDS_NPC = 17379406069905752682
WORLD_HASH = '6434b132b68a581a2046319c25795f9f5c1211ab2096b56898702a12542d83e8'
PLAN = {'label': LABEL, 'network_without_run': False,
        'creates': 'two fresh marked SEC_PLAYER human warriors; fresh TEST control unless verified class-systems-13 reuse',
        'checks': ['five vouchers, nearby NPC purchase, debit/sold/receipt once and replay',
                   'full backpack refusal then normal bracer equip and purchase retry',
                   'two personal stocks and foreign item GUID rejection',
                   'four vouchers versus unsold price six with free backpack space',
                   'ordinary Thunderfury level failure; authorized wrong-slot failure and main-hand success'],
        'excluded': ['real AP room/playthrough', 'cross-trade', 'combat procs', 'crash recovery']}


def emit(event, **values):
    print(json.dumps({'event': event, **values}, default=str, sort_keys=True), flush=True)


def fixture_guard(account, row, count, *, setup=False):
    require(account == 'TEST' if setup else account in ACCOUNTS, 'Protected account')
    guard_account(row, account, setup=setup)
    require(type(count) is int and 0 <= count < 10, 'No free character slot')


def released_class_result(path):
    result = json.loads(Path(path).read_text())
    require(result.get('result', {}).get('event') == 'PASS'
            and result.get('result', {}).get('gm_guid') in result.get('offline_fixture_guids', []),
            'Class-system result has not released TEST')
    return result


def merchant_guid(messages):
    text = '\n'.join(messages)
    require('Not in world' not in text and 'DB GUID: 9005000,' in text,
            'Merchant must be observed in the loaded map, not reconstructed from spawn ID')
    values = re.findall(r'GUID Full: 0x([0-9a-fA-F]{16}) Type: Creature Entry: 900500 ', text)
    require(len(values) == 1, 'No unique loaded merchant GUID')
    guid = int(values[0], 16)
    require(guid >> 48 == 0xF130 and (guid >> 24) & 0xFFFFFF == 900500,
            'Wrong merchant GUID layout')
    return guid


def teleport_command(name):
    require(isinstance(name, str) and re.fullmatch(r'Aps[a-z]{9}', name) is not None,
            'Only generated fixture names allowed')
    return '.tele name npc guid ' + name + ' 9005000'


def npc_selection(guid):
    require(type(guid) is int and guid >> 48 == 0xF130
            and (guid >> 24) & 0xFFFFFF == 900500 and guid & 0xFFFFFF,
            'Only merchant creature selection allowed')
    return struct.pack('<Q', guid)


def equip_packet(item_guid, slot):
    require(type(item_guid) is int and 0 < item_guid < 2**32
            and type(slot) is int and 0 <= slot < 19, 'Invalid own item equip action')
    return struct.pack('<QB', (0x4000 << 48) | item_guid, slot)


def observe(client):
    """Capture replies without changing the shared client's persistent ping schedule."""
    client.equip_errors, client.gossip = [], []
    process = client.process

    def capture(opcode, payload):
        if opcode == 0x112:
            require(bool(payload), 'Empty inventory error')
            client.equip_errors.append(payload[0])
            emit('inventory_result', code=payload[0], packet=payload.hex())
        elif opcode == 0x96:
            emit('chat_reply', packet=payload.hex())
        elif opcode == 0x17D:
            require(len(payload) >= 8, 'Truncated gossip response')
            client.gossip.append(struct.unpack_from('<Q', payload)[0])
            emit('gossip_reply', packet=payload.hex())
        process(opcode, payload)
    client.process = capture


def probe_source():
    files = {
        'src/server/scripts/Commands/cs_tele.cpp': ['HandleTeleNameNpcSpawnIdCommand', 'Player::SavePositionInDB',
            '{ "npc",    teleNameNpcCommandTable }', '{ "name",   teleNameCommandTable }',
            '{ "guid",   HandleTeleNameNpcSpawnIdCommand'],
        'src/server/scripts/Commands/cs_npc.cpp': ['GetCreatureFromPlayerMapByDbGuid', 'GetGUID().ToString()'],
        'src/server/scripts/Commands/cs_misc.cpp': ['HandleAddItemCommand', 'playerTarget->CanStoreNewItem'],
        'src/server/game/Entities/Object/ObjectGuid.h': ['uint64(entry) << 24', 'Unit           = 0xF130', 'Item           = 0x4000'],
        'src/server/game/Server/Packets/ItemPackets.cpp': ['_worldPacket >> ItemGuid;', '_worldPacket >> DestinationSlot;'],
        'src/server/game/Server/Protocol/Opcodes.h': ['CMSG_AUTOEQUIP_ITEM_SLOT                        = 0x10F', 'CMSG_SET_SELECTION                              = 0x13D', 'CMSG_GOSSIP_HELLO                               = 0x17B'],
    }
    hashes = {}
    for name, tokens in files.items():
        data = (SOURCE / name).read_bytes()
        require(all(t in data.decode() for t in tokens), 'Pinned command/packet layout changed: ' + name)
        hashes[name] = hashlib.sha256(data).hexdigest()
    for name in ('APMerchant.cpp', 'APMerchant.h', 'APDelivery.cpp', 'APDelivery.h'):
        data = (ROOT / 'src' / name).read_bytes()
        require(data == (SOURCE / 'modules/mod-archipelago/src' / name).read_bytes(), 'Module differs: ' + name)
        hashes[name] = hashlib.sha256(data).hexdigest()
    binary = subprocess.check_output(['docker', 'exec', 'wow-test-worldserver-1', 'sha256sum', '/proc/1/exe'], text=True, timeout=10)
    require(binary.split()[0] == WORLD_HASH, 'Running world binary is not pinned native2')
    return {'hashes': hashes, 'world': binary.strip()}


class MerchantRunner(Runner):
    def __init__(self, db, account, peer):
        require(account in ACCOUNTS and peer in ACCOUNTS and account != peer, 'Need two independent safe accounts')
        super().__init__(db, account)
        self.peer = peer
        self.created = set()
        self.stores = []

    @contextmanager
    def login(self, account, *, guid=None):
        require(account in (self.account, self.peer, 'TEST'), 'Protected login')
        if guid is None:
            require(account not in self.created, 'One fresh fixture per account per run')
            row = self.account_row(account)
            require(row is not None, 'Missing fixture account')
            count = self.query('SELECT COUNT(*) AS n FROM acore_characters.characters WHERE account=%s', (row['id'],))[0]['n']
            fixture_guard(account, row, count, setup=account == 'TEST')
            self.created.add(account)
        else:
            require(guid > 4 and guid in self.known, 'Protected or preexisting login')
            require(self.character(guid)['account'] == self.account_row(account)['id'], 'Wrong fixture owner')
        with super().login(account, guid=guid) as (client, chosen):
            observe(client)
            emit('login', account=account, guid=chosen, name=self.names[chosen], fresh=guid is None)
            yield client, chosen

    def setup(self, gm, guid, command):
        require(guid in self.known and guid > 4 and self.character(guid)['account'] in
                (self.account_row(self.account)['id'], self.account_row(self.peer)['id']), 'Unsafe setup target')
        gm.send(0x13D, selection_packet(guid))
        emit('gm_setup', target=guid, command=command, messages=gm.command(command))

    def teleport(self, gm, guid):
        self.offline(guid)
        self.setup(gm, guid, teleport_command(self.names[guid]))
        # The native command queues SavePositionInDB; its chat reply is not a commit fence.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            row = self.character(guid)
            if (row['map'] == 0 and abs(row['position_x'] + 8833.38) < .1
                    and abs(row['position_y'] - 628.628) < .1
                    and abs(row['position_z'] - 94.0066) < .1):
                return
            gm.stay(.25)
        raise RuntimeError('Offline native teleport not durable within 10 seconds')

    def saved(self, guid, binding):
        owner = self.account
        self.account = next(a for a in (owner, self.peer) if self.account_row(a)['id'] == self.character(guid)['account'])
        try:
            return self.snapshot(guid, binding)
        finally:
            self.account = owner

    def economic(self, guid, binding):
        snap = self.saved(guid, binding)
        return {k: snap[k] for k in ('progress', 'rewards', 'purchases', 'stock', 'authorized')}

    def wait_rewards(self, client, binding, count):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            rows = self.query('SELECT applied FROM acore_characters.mod_archipelago_reward WHERE binding_id=%s', (binding,))
            if len(rows) == count and all(r['applied'] for r in rows):
                return
            client.stay(.25)
        raise RuntimeError('Native delivery timeout')

    def bind(self, account, guid, codes, catalog):
        from bridge.v2 import Store
        require(self.offline(guid)['level'] == 1, 'Fixture must be fresh level 1')
        require(not self.query('SELECT id FROM acore_characters.mod_archipelago_binding WHERE character_guid=%s', (guid,)), 'Do not reset history')
        seed = 'fabricated-merchant-' + secrets.token_hex(12)
        raw = manifest_fixture(catalog, seed)
        store = Store(dict(host='127.0.0.1', port=13317, user='root', database='acore_characters'), guid, catalog)
        self.stores.append(store)
        binding = store.bind(seed, 0, 1, raw)
        store.status('disconnected')
        items = [{'class': 'NetworkItem', 'item': c, 'location': -1, 'player': 0, 'flags': 0} for c in codes]
        require(store.receive(0, items), 'Fabricated ingress rejected')
        emit('fabricated_ingress', account=account, guid=guid, binding=binding, seed=seed, codes=codes, label=LABEL)
        return binding, store, items

    def reuse_control(self):
        files = {name: (CONTROL_EVIDENCE / name).read_bytes()
                 for name in ('summary.json', 'before.json', 'run.jsonl')}
        summary = json.loads(files['summary.json'])
        before = json.loads(files['before.json'])
        events = [json.loads(line) for line in files['run.jsonl'].splitlines() if line.strip()]
        require(summary.get('result', {}).get('event') == 'PASS'
                and summary['result'].get('gm_guid') == CONTROL_GUID
                and CONTROL_GUID in summary.get('offline_fixture_guids', []), 'Control release evidence mismatch')
        require(all(r['guid'] != CONTROL_GUID and r['name'] != CONTROL_NAME for r in before['characters']),
                'Control existed before trusted creation')
        creations = [e for e in events if e.get('event') == 'gm_fixture']
        require(creations == [dict(event='gm_fixture', guid=CONTROL_GUID, name=CONTROL_NAME)],
                'Trusted control creation evidence mismatch')
        account = self.account_row('TEST')
        guard_account(account, 'TEST', setup=True)
        require(account['id'] == 1, 'Control account ID changed')
        row = self.character(CONTROL_GUID)
        require(CONTROL_GUID > 4 and row is not None
                and all(row.get(k) == v for k, v in dict(guid=CONTROL_GUID, name=CONTROL_NAME,
                    account=1, race=1, **{'class': 1}, level=1, online=0).items()),
                'Owned control profile mismatch')
        require(not self.query('SELECT id FROM acore_characters.mod_archipelago_binding WHERE character_guid=%s',
                               (CONTROL_GUID,)), 'Control has AP binding')
        self.known.add(CONTROL_GUID)
        self.names[CONTROL_GUID] = CONTROL_NAME
        emit('verified_control_reuse', guid=CONTROL_GUID, name=CONTROL_NAME, account='TEST',
             evidence_sha256={name: hashlib.sha256(data).hexdigest() for name, data in files.items()})
        return CONTROL_GUID

    def reuse_funds_peer(self):
        """Only the parent's authorized peer from the pinned merchant PASS can enter."""
        data = FUNDS_RUN.read_bytes()
        require(hashlib.sha256(data).hexdigest() == FUNDS_HASH, 'Merchant ownership evidence hash mismatch')
        events = [json.loads(line) for line in data.splitlines() if line.strip()]
        summary_data = (FUNDS_RUN.parent.parent / 'summary.json').read_bytes()
        summary = json.loads(summary_data)
        passes = [e for e in events if e.get('event') == 'PASS']
        require(len(passes) == 1 and summary.get('result') == passes[0]
                and summary.get('run_sha256') == FUNDS_HASH
                and passes[0].get('peer') == 23 and passes[0].get('peer_binding') == 13
                and 23 in summary.get('offline_fixture_guids', []), 'Merchant PASS ownership mismatch')
        creations = [e for e in events if e.get('event') == 'login' and e.get('fresh')
                     and (e.get('guid') == 23 or e.get('name') == FUNDS_NAME)]
        require(creations == [dict(event='login', account='APV2E', fresh=True, guid=23, name=FUNDS_NAME)],
                'No unique trusted peer creation')
        ingress = [e for e in events if e.get('event') == 'fabricated_ingress' and e.get('guid') == 23]
        require(len(ingress) == 1 and ingress[0]['binding'] == 13
                and ingress[0]['account'] == 'APV2E', 'Peer binding evidence mismatch')
        require((self.account, self.peer) == ('APV2D', 'APV2E'), 'Funds reuse requires original accounts')
        account = self.account_row('APV2E')
        guard_account(account, 'APV2E')
        require(account['id'] == 6, 'Peer account changed')
        row = self.character(23)
        require(row is not None and all(row.get(k) == v for k, v in
                dict(guid=23, name=FUNDS_NAME, account=6, race=1, **{'class': 1}, level=1, online=0).items()),
                'Owned peer profile mismatch')
        bindings = self.query('SELECT id,character_guid,character_name,character_account,seed_name,class_id,race_id '
                              'FROM acore_characters.mod_archipelago_binding WHERE character_guid=%s', (23,))
        require(bindings == [dict(id=13, character_guid=23, character_name=FUNDS_NAME,
                    character_account=6, seed_name=ingress[0]['seed'], class_id=1, race_id=1)],
                'Owned peer binding mismatch')
        self.known.add(23)
        self.names[23] = FUNDS_NAME
        emit('verified_funds_reuse', guid=23, account='APV2E', name=FUNDS_NAME, binding=13,
             evidence_sha256={'run.jsonl': FUNDS_HASH, 'summary.json': hashlib.sha256(summary_data).hexdigest()})
        return 23, 13

    def insufficient_funds(self, guid, binding, npc):
        before = self.saved(guid, binding)
        require(len(before['progress']) == 1 and before['progress'][0]['vouchers'] == 4,
                'Funds assertion requires four vouchers')
        free = 16 - sum(r['bag'] == 0 and 23 <= r['slot'] < 39 for r in before['inventory'])
        require(0 < free <= 16 and not any(r['bag'] for r in before['inventory']),
                'Funds assertion requires free backpack space')
        candidates = [r for r in before['stock'] if not r['sold'] and r['price'] == 6]
        require(bool(candidates), 'No unsold six-voucher stock')
        stock = candidates[0]
        template = self.query('SELECT entry FROM acore_world.item_template WHERE entry=%s', (stock['item_entry'],))
        require(template == [{'entry': stock['item_entry']}], 'Stock not in real item catalog')
        emit('funds_before', guid=guid, binding=binding, free_backpack=free, selected=stock, snapshot=before)
        with self.login(self.peer, guid=guid) as (player, _):
            player.send(0x13D, npc_selection(npc))
            player.send(0x17B, npc_selection(npc))
            player.stay(.5)
            require(npc in player.gossip, 'No actual nearby merchant gossip reply')
            messages = player.command('.archipelago buy ' + str(stock['stock_index']))
            emit('funds_protocol', guid=guid, npc=npc, stock_index=stock['stock_index'], messages=messages)
            require(any('Entry sold, invalid, or not enough vouchers.' in m for m in messages),
                    'Native insufficient-funds refusal missing')
        after = self.saved(guid, binding)
        emit('funds_after', guid=guid, binding=binding, snapshot=after)
        unchanged = ('progress', 'rewards', 'purchases', 'stock', 'authorized', 'inventory', 'items')
        require(all(before[k] == after[k] for k in unchanged), 'Funds refusal changed items or economics')
        emit('insufficient_funds_refusal', guid=guid, binding=binding, vouchers=4, price=6,
             stock_index=stock['stock_index'], item_entry=stock['item_entry'], free_backpack=free,
             persisted_after_logout=True)

    def execute_funds(self):
        protected = self.query('SELECT * FROM acore_characters.characters WHERE guid IN (1,2,3,4) ORDER BY guid')
        population = self.query('SELECT guid,name,account FROM acore_characters.characters ORDER BY guid')
        guid, binding = self.reuse_funds_peer()
        self.insufficient_funds(guid, binding, FUNDS_NPC)
        require(protected == self.query('SELECT * FROM acore_characters.characters WHERE guid IN (1,2,3,4) ORDER BY guid'),
                'Original characters changed')
        require(population == self.query('SELECT guid,name,account FROM acore_characters.characters ORDER BY guid'),
                'Character population changed')
        self.offline(guid)
        emit('PASS', check='native insufficient funds', guid=guid, binding=binding,
             no_characters_created=True, no_sql_writes=True, missing=PLAN['excluded'])

    def execute(self, *, reuse_control=False):
        catalog = Catalog()
        protected = self.query('SELECT * FROM acore_characters.characters WHERE guid IN (1,2,3,4) ORDER BY guid')
        # Only the explicitly authorized control can avoid the fresh-character capacity guard.
        control = self.reuse_control() if reuse_control else None
        for account in (self.account, self.peer, 'TEST'):
            if account == 'TEST' and control is not None:
                continue
            row = self.account_row(account)
            require(row is not None, 'Missing account')
            count = self.query('SELECT COUNT(*) AS n FROM acore_characters.characters WHERE account=%s', (row['id'],))[0]['n']
            fixture_guard(account, row, count, setup=account == 'TEST')
        for account in (self.account, self.peer):
            with self.login(account) as (_, guid):
                if account == self.account:
                    primary = guid
                else:
                    peer = guid
        binding, store, ingress = self.bind(self.account, primary, [919100033, 919419019], catalog)
        other, peer_store, peer_ingress = self.bind(self.peer, peer, [919100033], catalog)
        with self.login('TEST', guid=control) as (gm, gm_guid):
            for account, guid, bid, count in ((self.account, primary, binding, 2), (self.peer, peer, other, 1)):
                with self.login(account, guid=guid) as (player, _):
                    self.wait_rewards(player, bid, count)
                    require(any('Vouchers 5' in m for m in player.command('.archipelago status')), 'Not five native vouchers')
                if guid == primary:
                    self.teleport(gm, guid)
            initial = self.economic(primary, binding)
            peer_initial = self.economic(peer, other)
            stock = next(r for r in initial['stock'] if r['price'] <= 5)
            index, entry, price = stock['stock_index'], stock['item_entry'], stock['price']
            legend = next(r['item_guid'] for r in initial['authorized'] if r['item_entry'] == 19019)
            with self.login(self.account, guid=primary) as (player, _):
                # Source-backed runtime GUID from the loaded creature, never assume spawn ID == counter.
                npc = merchant_guid(gm.command('.npc info 9005000'))
                emit('merchant', runtime_guid=npc, spawn=9005000, entry=900500)
                player.send(0x13D, struct.pack('<Q', 0))
                require(any('Select a nearby' in m for m in player.command('.archipelago buy ' + str(index))), 'No-selection guard failed')
                player.send(0x13D, npc_selection(npc))
                player.send(0x17B, npc_selection(npc))
                player.stay(.5)
                require(npc in player.gossip, 'No actual nearby merchant gossip reply')
            # Thunderfury is unique; use the other fresh level-1 human warrior for the ordinary copy.
            with self.login(self.peer, guid=peer) as (player, _):
                self.setup(gm, peer, '.additem 19019 1')
                player.stay(.5)
            normal_snap = self.saved(peer, other)
            normal = [i['guid'] for i in normal_snap['items'] if i['itemEntry'] == 19019 and i['guid'] != legend]
            require(len(normal) == 1 and normal[0] not in {r['item_guid'] for r in normal_snap['authorized']}, 'Ordinary copy not distinct/unauthorized')
            require(self.economic(peer, other) == peer_initial and self.economic(primary, binding) == initial,
                    'Setup changed economics')
            with self.login(self.peer, guid=peer) as (player, _):
                player.send(0x10F, equip_packet(normal[0], 15))
                player.stay(.5)
                require(1 in player.equip_errors, 'Ordinary Thunderfury did not fail required level')
            require(self.saved(peer, other)['inventory'] == normal_snap['inventory'], 'Ordinary copy escaped backpack')
            emit('ordinary_copy_refusal', guid=peer, item=normal[0], error=1)
            with self.login(self.account, guid=primary) as (player, _):
                messages = player.command('.archipelago equip ' + str(legend) + ' 0')
                require(any('Equip failed' in m for m in messages), 'Authorized wrong-slot unexpectedly accepted')
                require(any(code in (3, 20) for code in player.equip_errors), 'Missing normal wrong-slot constraint')
                player.command('.archipelago equip ' + str(legend) + ' 15')
            snap = self.saved(primary, binding)
            require(any(r['item'] == legend and r['bag'] == 0 and r['slot'] == 15 for r in snap['inventory']), 'Level-1 authorized equip did not persist')
            require(not any(r['bag'] == 0 and r['slot'] == 8 for r in snap['inventory']), 'Retry requires empty wrist slot')
            free = 16 - sum(r['bag'] == 0 and 23 <= r['slot'] < 39 for r in snap['inventory'])
            require(0 < free <= 16 and not any(r['bag'] for r in snap['inventory']), 'Unexpected starting bag layout')
            with self.login(self.account, guid=primary) as (player, _):
                self.setup(gm, primary, '.additem 6070 ' + str(free))
                player.stay(.5)
            full = self.saved(primary, binding)
            require(sum(r['bag'] == 0 and 23 <= r['slot'] < 39 for r in full['inventory']) == 16, 'Backpack not actually full')
            bracer = next(i['guid'] for i in full['items'] if i['itemEntry'] == 6070)
            with self.login(self.account, guid=primary) as (player, _):
                player.send(0x13D, npc_selection(npc))
                messages = player.command('.archipelago buy ' + str(index))
                require(any('Purchase not completed' in m for m in messages), 'Full-bag purchase was not refused')
            require(self.economic(primary, binding) == initial, 'Full-bag refusal changed economics')
            require(self.saved(primary, binding)['inventory'] == full['inventory'], 'Failed purchase changed item placement')
            emit('full_bag_refusal', guid=primary, binding=binding, occupied=16)
            with self.login(self.account, guid=primary) as (player, _):
                player.send(0x10F, equip_packet(bracer, 8))
                player.stay(.5)
                player.send(0x13D, npc_selection(npc))
                require(any('Purchase complete.' in m for m in player.command('.archipelago buy ' + str(index))), 'Positive native purchase failed')
            bought = self.saved(primary, binding)
            purchases = bought['purchases']
            require(len(purchases) == 1 and purchases[0]['item_entry'] == entry and purchases[0]['price'] == price, 'Purchase receipt differs')
            purchased = purchases[0]['item_guid']
            require(bought['progress'][0]['vouchers'] == 5 - price and sum(r['sold'] for r in bought['stock']) == 1, 'Not exactly one debit/sold row')
            require(any(i['guid'] == purchased and i['itemEntry'] == entry and i['owner_guid'] == primary and i['count'] == 1 and i['flags'] & 1 and not i['flags'] & (256 | 4096) for i in bought['items']), 'Missing bound purchased item')
            require(any(r['item_guid'] == purchased and r['item_entry'] == entry for r in bought['authorized']), 'Purchase not authorized')
            require(self.economic(peer, other) == peer_initial, 'Primary purchase changed peer stock/balance')
            once = self.economic(primary, binding)
            require(store.receive(0, ingress), 'Same ingress replay rejected')
            with self.login(self.account, guid=primary) as (player, _):
                player.send(0x13D, npc_selection(npc))
                require(any('Entry sold' in m for m in player.command('.archipelago buy ' + str(index))), 'Sold replay not refused')
            require(self.economic(primary, binding) == once, 'Replay debited or created a second item')
            require(self.saved(primary, binding)['inventory'] == bought['inventory'], 'Replay changed inventory')
            with self.login(self.peer, guid=peer) as (player, _):
                row = self.character(peer)
                require(abs(row['position_x'] + 8833.38) > 100, 'Remote fixture unexpectedly nearby')
                player.send(0x13D, npc_selection(npc))
                require(any('Select a nearby' in m for m in player.command('.archipelago buy ' + str(index))), 'Far merchant selection was not refused')
            require(self.economic(peer, other) == peer_initial, 'Remote purchase changed peer stock')
            self.teleport(gm, peer)
            with self.login(self.peer, guid=peer) as (player, _):
                require(any('Equip failed' in m for m in player.command('.archipelago equip ' + str(legend) + ' 15')), 'Foreign authorized GUID accepted')
                player.send(0x13D, npc_selection(npc))
                require(any('Purchase complete.' in m for m in player.command('.archipelago buy ' + str(index))), 'Peer could not buy its unsold personal copy')
            peer_bought = self.saved(peer, other)
            require(len(peer_bought['purchases']) == 1 and peer_bought['purchases'][0]['item_guid'] != purchased
                    and peer_bought['purchases'][0]['item_entry'] == entry
                    and peer_bought['progress'][0]['vouchers'] == 5 - price
                    and sum(r['sold'] for r in peer_bought['stock']) == 1, 'Peer personal purchase differs')
            require(self.economic(primary, binding) == once, 'Peer purchase changed primary stock')
            self.insufficient_funds(peer, other, npc)
            require(self.economic(primary, binding) == once, 'Funds refusal changed primary economics')
            emit('saved_evidence', primary=bought, peer=peer_bought)
        require(protected == self.query('SELECT * FROM acore_characters.characters WHERE guid IN (1,2,3,4) ORDER BY guid'), 'Original characters changed')
        for guid in (primary, peer, gm_guid):
            self.offline(guid)
        emit('PASS', label=LABEL, primary=primary, peer=peer, gm=gm_guid, binding=binding,
             peer_binding=other, stock_index=index, price=price, purchased=purchased,
             ordinary_thunderfury=normal[0], authorized_thunderfury=legend, missing=PLAN['excluded'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--account', choices=ACCOUNTS, default='APV2D')
    parser.add_argument('--peer', choices=ACCOUNTS, default='APV2E')
    parser.add_argument('--reuse-control', choices=('class-systems-13',),
                        help='reuse only the authorized class-system GM with trusted creation evidence')
    parser.add_argument('--funds-only', choices=('owned-peer-23',),
                        help='only the authorized GUID 23 from the pinned merchant PASS; no setup or creation')
    parser.add_argument('--class-result', type=Path, default=ROOT / '.local/class-systems/summary.json')
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(PLAN, indent=2))
        return 0
    require(args.account != args.peer, 'Need distinct fixture accounts')
    require(os.environ.get('WOWPILAGO_TEST_ACCOUNT_PASSWORD') == 'test-only', 'Set WOWPILAGO_TEST_ACCOUNT_PASSWORD=test-only')
    require(os.environ.get('WOWPILAGO_DB_PASSWORD') == 'test-only', 'Set WOWPILAGO_DB_PASSWORD=test-only for private realm')
    if not args.funds_only:
        released_class_result(args.class_result)
    emit('pinned_source', **probe_source())
    import pymysql
    with pymysql.connect(host='127.0.0.1', port=13317, user='root', password=os.environ['WOWPILAGO_DB_PASSWORD'],
                         autocommit=True, cursorclass=pymysql.cursors.DictCursor,
                         connect_timeout=5, read_timeout=15, write_timeout=15) as db:
        runner = MerchantRunner(db, args.account, args.peer)
        try:
            if args.funds_only:
                runner.execute_funds()
            else:
                runner.execute(reuse_control=args.reuse_control is not None)
        finally:
            for store in runner.stores:
                store.close()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        emit('FAIL', error=str(exc), history='All fixtures, receipts and failed attempts preserved. No repair/reset.')
        sys.exit(1)
