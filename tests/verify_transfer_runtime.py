"""Owned 22/23 native mail and auction refusals; no successful send or listing."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch
import json
import os
import re
import socket
import struct
import sys

from verify_runtime import SmokeClient, guard_account, guard_character, require, say_packet
from verify_trade_runtime import TradeRunner, FIXTURES, digest, save
from verify_merchant_runtime import MerchantRunner, CONTROL_NAME
import verify_artisan_runtime as artisan

SOURCE = artisan.SOURCE
WORLD_HASH = '3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809'

ROOT = SOURCE.parents[3]
OUTPUT = ROOT / '.local/transfer-fixed-plan'
MANIFEST_HASH = '6ac13239c2b11940904ece49ea6064c72980e433d6ef06aff587f36babc51553'
PATCH_HASH = '76342b88b9864f85525771ba51de7c2b78467343027075b83184bc76356aca6c'
MAIL_POS = (-8815.17, 652.927, 94.8966)
AH_POS = (-8821.53, 659.886, 97.4645)
COMMANDS = {'.summon Apsqlkruenob', '.gobject info guid 100156',
            '.npc info 79705', *('.go xyz ' + ' '.join(map(str, pos)) + ' 0' for pos in (MAIL_POS, AH_POS))}
PLAN = dict(network_without_run=False, fixtures=[22, 23], gm=13,
            setup='reuse exact 10000 copper attestation; native online teleports before phase baselines',
            requires='fresh parent release.json, explicit release of all native matrix ownership, all characters/accounts offline',
            checks=['AP 269/285 native mail bound errors', 'AP 269/285 native auction rejection',
                    'mail unbound-first validation, auction hello + nonposting ordinary count validation',
                    'unchanged phase snapshots, no debit, no mail attachments or auction listings'])
LOG = None


def emit(event, **values):
    line = json.dumps(dict(event=event, **values), default=str, sort_keys=True)
    print(line, flush=True)
    if LOG:
        LOG.write(line + '\n')
        LOG.flush()


def mail_packet(mailbox, items):
    require(type(mailbox) is int and mailbox >> 48 == 0xF110 and
            (mailbox >> 24) & 0xFFFFFF == 195603, 'Unobserved mailbox type')
    require(items in ((269,), (285,), (256, 269), (256, 285)), 'No successful mail route permitted')
    return (struct.pack('<Q', mailbox) + b'Apsgiylwpuwg\0transfer binding probe\0fixture-only negative\0'
            + struct.pack('<IIB', 41, 0, len(items))
            + b''.join(struct.pack('<BQ', n, (0x4000 << 48) | item) for n, item in enumerate(items))
            + struct.pack('<IIQB', 0, 0, 0, 0))


def auction_packet(npc, item, count=1):
    require(type(npc) is int and npc >> 48 == 0xF130 and (npc >> 24) & 0xFFFFFF == 8719,
            'Unobserved auctioneer type')
    require((item, count) in ((269, 1), (285, 1), (256, 2)), 'No ordinary listing permitted')
    return struct.pack('<QIQIIII', npc, 1, (0x4000 << 48) | item, count, 100, 0, 720)


def packed_guid(data):
    require(bool(data), 'Missing packed GUID')
    offset, guid = 1, 0
    for n in range(8):
        if data[0] & (1 << n):
            require(offset < len(data), 'Truncated packed GUID')
            guid |= data[offset] << (8 * n)
            offset += 1
    return guid, offset


def observed_guid(messages, kind, entry):
    token = 'Gameobject' if kind == 'GameObject' else kind
    values = re.findall(r'GUID Full: 0x([0-9a-fA-F]{16}) Type: ' + token + r' Entry: ' + str(entry) + r'\b', '\n'.join(messages))
    require(len(values) == 1 and 'Not in world' not in '\n'.join(messages), 'No unique native loaded GUID')
    guid = int(values[0], 16)
    require(guid >> 48 == (0xF110 if kind == 'GameObject' else 0xF130)
            and (guid >> 24) & 0xFFFFFF == entry, 'Native GUID type mismatch')
    return guid


class TransferClient(SmokeClient):
    def __init__(self, sock, authorize, guid):
        self.guid, self.world = guid, None
        self.mailbox = self.auctioneer = None
        self.replies, self.hellos = [], []
        self.teleport_ack = None
        super().__init__(sock, authorize)

    def send(self, opcode, payload=b''):
        require(self.guid in (13, 22), 'Protected session')
        if opcode == 0x95:
            require(self.guid == 13 and payload in {say_packet(c) for c in COMMANDS}, 'Forbidden GM command')
        elif opcode == 0x13D:
            require(self.guid == 13 and payload == struct.pack('<Q', 22), 'Forbidden selection')
        elif opcode == 0x238:
            require(self.guid == 22 and self.mailbox is not None and payload in
                    {mail_packet(self.mailbox, i) for i in ((269,), (285,), (256, 269), (256, 285))}, 'Forbidden mail')
        elif opcode in (0x255, 0x256):
            require(self.guid == 22 and self.auctioneer is not None, 'Unobserved auctioneer')
            allowed = {struct.pack('<Q', self.auctioneer)} if opcode == 0x255 else {
                auction_packet(self.auctioneer, i, c) for i, c in ((269, 1), (285, 1), (256, 2))}
            require(payload in allowed, 'Forbidden auction operation')
        elif opcode == 0xC7:
            require(payload == self.teleport_ack and self.teleport_ack is not None, 'Unsolicited teleport ack')
            self.teleport_ack = None
        else:
            require(opcode in (0x1ED, 0x37, 0x3D, 0x1DC, 0x391, 0x4B), 'Forbidden opcode including creation')
            if opcode == 0x3D:
                require(payload == struct.pack('<Q', self.guid), 'Wrong login GUID')
            if opcode in (0x37, 0x4B):
                require(not payload, 'Unexpected payload')
        emit('packet', guid=self.guid, direction='CMSG', opcode=hex(opcode), raw=payload.hex())
        super().send(opcode, payload)

    def receive(self):
        opcode, payload = super().receive()
        emit('packet', guid=self.guid, direction='SMSG', opcode=hex(opcode), raw=payload.hex())
        return opcode, payload

    def process(self, opcode, payload):
        if opcode == 0x236:
            require(len(payload) == 20, 'Invalid world location')
            self.world = struct.unpack('<Iffff', payload)
        elif opcode == 0xC7:
            guid, offset = packed_guid(payload)
            require(guid == self.guid and len(payload) >= offset + 30 and self.world is not None, 'Bad near teleport')
            sequence, = struct.unpack_from('<I', payload, offset)
            self.world = (self.world[0], *struct.unpack_from('<ffff', payload, offset + 14))
            self.teleport_ack = payload[:offset] + struct.pack('<II', sequence, 0)
            self.send(0xC7, self.teleport_ack)
            emit('online_teleport', guid=guid, world=self.world)
        elif opcode == 0x255:
            require(len(payload) == 13, 'Invalid auction hello')
            hello = struct.unpack('<QIB', payload)
            self.hellos.append(hello)
            emit('auction_hello', guid=self.guid, reply=hello)
        elif opcode in (0x239, 0x25B):
            require(len(payload) == (16 if opcode == 0x239 else 12), 'Unexpected transfer result size')
            result = struct.unpack('<' + 'I' * (len(payload) // 4), payload)
            self.replies.append((opcode, result))
            emit('transfer_result', guid=self.guid, opcode=hex(opcode), result=result)
        super().process(opcode, payload)


def probe_source():
    evidence = artisan.build_evidence()
    manifest = json.loads((artisan.BUILD / 'manifest.json').read_text())
    require(evidence['manifest_sha256'] == MANIFEST_HASH and evidence['world_sha256'] == WORLD_HASH
            and manifest['patch_sha256'] == PATCH_HASH, 'Fixed candidate identity changed')
    require(digest((ROOT / 'patches/azerothcore-v2.patch').read_bytes()) == PATCH_HASH
            and digest((artisan.BUILD / 'base-manifest.json').read_bytes()) == manifest['base_manifest_sha256'],
            'Combined patch/base provenance changed')
    inventory = json.loads((artisan.BUILD / 'source-files.sha256.json').read_text())
    hashes = {}
    for name in ('game/Handlers/MailHandler.cpp', 'game/Handlers/AuctionHouseHandler.cpp',
                 'game/Handlers/MovementHandler.cpp', 'game/Entities/Item/Item.cpp',
                 'game/Entities/Item/Item.h', 'game/Entities/Item/ItemTemplate.h',
                 'game/Entities/Player/Player.cpp', 'game/Entities/Player/PlayerStorage.cpp',
                 'game/AuctionHouse/AuctionHouseMgr.h', 'game/AuctionHouse/AuctionHouseMgr.cpp',
                 'game/Server/Protocol/Opcodes.h',
                 'shared/SharedDefines.h', 'scripts/Commands/cs_gobject.cpp', 'scripts/Commands/cs_npc.cpp',
                 'scripts/Commands/cs_go.cpp', 'scripts/Commands/cs_misc.cpp', 'scripts/Commands/cs_modify.cpp',
                 'scripts/World/server_mail.cpp', 'game/Handlers/ItemHandler.cpp',
                 'game/Server/Packets/ItemPackets.cpp'):
        path = 'src/server/' + name
        hashes[name] = digest((SOURCE / path).read_bytes())
        require(hashes[name] == inventory[path], 'Native source differs: ' + path)
    return dict(**evidence, hashes=hashes, patch_sha256=PATCH_HASH,
                base_manifest_sha256=manifest['base_manifest_sha256'])


def parent_release():
    release = json.loads((OUTPUT / 'release.json').read_text())
    now = datetime.now(timezone.utc)
    issued = datetime.fromisoformat(release['issued_utc'])
    expires = datetime.fromisoformat(release['expires_utc'])
    require(issued.tzinfo is not None and expires.tzinfo is not None
            and issued <= now < expires and (expires - issued).total_seconds() <= 1800,
            'Fresh parent release required, maximum 30 minutes')
    require(all(release.get(k) is True for k in
                ('owned_release', 'gui40_released', 'mail46_released', 'native_matrix_released'))
            and release.get('world_sha256') == WORLD_HASH and bool(release.get('release_id')),
            'Explicit parent and all native matrix ownership release required; quiet is not release')
    return release


def runtime_evidence(evidence):
    parent_release()
    with patch.object(artisan, 'OUTPUT', OUTPUT):
        return artisan.runtime_evidence(evidence)


class TransferRunner(TradeRunner):
    reuse_control = MerchantRunner.reuse_control
    client_type = TransferClient

    def preflight(self):
        parent_release()
        require(not self.query('SELECT guid FROM acore_characters.characters WHERE online<>0')
                and not self.query('SELECT id FROM acore_auth.account WHERE online<>0'),
                'All characters and accounts must be offline after matrix release')

    @contextmanager
    def login(self, guid):
        from realm_client import authenticate
        require(guid in self.known and guid in (13, 22, 23), 'Unverified fixture')
        parent_release()
        account, account_id, name = ('TEST', 1, CONTROL_NAME) if guid == 13 else FIXTURES[guid][:3]
        guard_account(self.account_row(account), account, setup=guid == 13)
        row = self.character(guid)
        guard_character(row, account_id, name, self.known)
        require(row['online'] == 0, 'Fixture busy')

        def authorize(candidate, events):
            require(candidate == guid and not any(e.startswith('CREATED ') for e in events), 'Existing fixture only')
            guard_character(self.character(candidate), account_id, name, self.known)
        auth = authenticate(account, 'TEST' if guid == 13 else os.environ['WOWPILAGO_TEST_ACCOUNT_PASSWORD'],
                            ready_timeout=30)
        realm = next((r for r in auth.realms if not r.locked and not r.flags & 3), None)
        require(realm is not None, 'No ready realm')
        try:
            with socket.create_connection(('127.0.0.1', 8085), timeout=10) as sock:
                client = self.client_type(sock, authorize, guid)
                try:
                    chosen = client.connect(account, auth, realm, name, race=1, class_id=1)
                    require(chosen.guid == guid, 'Wrong fixture')
                    client.stay(.5)
                    yield client
                finally:
                    if client.login:
                        client.logout()
                        emit('normal_logout', guid=guid)
        finally:
            self.offline(guid)

    def saved(self):
        result = super().saved()
        result.update(mail=self.query('SELECT * FROM acore_characters.mail WHERE sender IN (22,23) OR receiver IN (22,23) ORDER BY id'),
                      attachments=self.query('SELECT * FROM acore_characters.mail_items WHERE receiver IN (22,23) OR item_guid IN (256,269,285) ORDER BY mail_id,item_guid'),
                      auctions=self.query('SELECT * FROM acore_characters.auctionhouse WHERE itemowner IN (22,23) OR itemguid IN (256,269,285) ORDER BY id'),
                      tracked_items=self.query('SELECT * FROM acore_characters.item_instance WHERE guid IN (256,269,285) ORDER BY guid'))
        return result

    def prepare(self, before):
        controls = super().prepare(before)
        items = before['tracked_items']
        require(before['fixtures']['22']['character'][0]['money'] == 10000,
                'Preserve exact prior native money setup; never top up')
        require(len(items) == 3 and all(i['owner_guid'] == 22 and i['count'] == 1
                and i['duration'] == 0 for i in items), 'Tracked item owner/count/duration changed')
        require(not before['auctions'] and not before['attachments'], 'Existing fixture listing/attachment')
        require({i['guid']: i['flags'] for i in items} == {256: 0, 269: 1, 285: 1}
                and all(i['enchantments'].split() and not any(map(int, i['enchantments'].split()))
                        for i in items), 'Binding/enchantment preconditions changed')
        templates = self.query('SELECT entry,name,class,Flags,flagsExtra,bonding,RequiredLevel,SellPrice,stackable '
                               'FROM acore_world.item_template WHERE entry IN (49778,19019,756) ORDER BY entry')
        emit('transfer_templates', rows=templates)
        require(len(templates) == 3 and all(t['class'] == 2 and not t['Flags'] & (2 | 0x08000000)
                for t in templates), 'Unexpected bag/conjured/account-bound item template')
        return controls

    def setup_phase(self, phase):
        position = MAIL_POS if phase == 'mail' else AH_POS
        if phase == 'mail':
            rows = self.query('SELECT g.guid,g.id,g.map,g.position_x,g.position_y,g.position_z,t.type '
                              'FROM acore_world.gameobject g JOIN acore_world.gameobject_template t ON t.entry=g.id WHERE g.guid=100156')
            require(len(rows) == 1 and rows[0]['id'] == 195603 and rows[0]['type'] == 19, 'Mailbox spawn changed')
        else:
            rows = self.query('SELECT c.guid,c.id,c.map,c.position_x,c.position_y,c.position_z,t.npcflag '
                              'FROM acore_world.creature c JOIN acore_world.creature_template t ON t.entry=c.id WHERE c.guid=79705')
            require(len(rows) == 1 and rows[0]['id'] == 8719 and rows[0]['npcflag'] & 2097152, 'Auctioneer spawn changed')
        require(rows[0]['map'] == 0 and all(abs(rows[0]['position_' + n] - position[i]) < .01
                for i, n in enumerate(('x', 'y', 'z'))), 'Spawn coordinates changed')
        emit('spawn_select', phase=phase, rows=rows)
        with self.login(13) as gm, self.login(22) as player:
            gm.send(0x13D, struct.pack('<Q', 22))
            if phase == 'mail':
                money = self.character(22)['money']
                require(money == 10000, 'Preserve prior setup funds; never add again')
                proof = ROOT / '.local/transfer-live/20261019T183515.560707Z/run.jsonl'
                data = proof.read_bytes()
                require(digest(data) == '81a103ca41e7f1edcfec64a30c63a4065dd07bf278062fddfe90555cd870a286',
                        'Money needs exact prior native setup proof')
                events = [json.loads(line) for line in data.splitlines()]
                require(sum(e.get('event') == 'gm_setup' and e.get('target') == 22 and
                            e.get('command') == '.modify money 10000' for e in events) == 1
                        and not any(e.get('direction') == 'CMSG' and e.get('opcode') in
                                    ('0x238', '0x256') for e in events), 'Prior setup proof mismatch')
                emit('reuse_logged_native_money', target=22, copper=money, proof=str(proof), sha256=digest(data))
            for command in ('.go xyz ' + ' '.join(map(str, position)) + ' 0', '.summon Apsqlkruenob'):
                emit('gm_setup', target=13 if command.startswith('.go ') else 22,
                     command=command, messages=gm.command(command))
                player.stay(.5)
                gm.stay(.5)
            for client in (gm, player):
                require(client.world and client.world[0] == 0 and
                        sum((client.world[n + 1] - position[n]) ** 2 for n in range(3)) <= 25,
                        'Online teleport not acknowledged within native interaction distance')
            command = '.gobject info guid 100156' if phase == 'mail' else '.npc info 79705'
            messages = gm.command(command)
            emit('native_guid_query', command=command, messages=messages)
            guid = observed_guid(messages, 'GameObject' if phase == 'mail' else 'Creature', 195603 if phase == 'mail' else 8719)
        require(self.offline(22)['money'] >= 100, 'Postage/deposit baseline needs at least 1 silver')
        return guid

    def attempt(self, player, opcode, packet, expected, label):
        player.replies.clear()
        player.send(opcode, packet)
        player.stay(.6)
        require(player.replies == [(0x239 if opcode == 0x238 else 0x25B, expected)], 'Wrong native result: ' + label)
        emit('refusal', label=label, result=expected)

    def phase(self, phase, native_guid, output):
        before = self.saved()
        self.prepare(before)
        save(output / (phase + '-before.json'), before)
        emit('before_select', phase=phase, snapshot=before)
        try:
            with self.login(22) as player:
                if phase == 'mail':
                    player.mailbox = native_guid
                    for item in (269, 285):
                        for items in ((item,), (256, item)):
                            self.attempt(player, 0x238, mail_packet(native_guid, items), (0, 0, 1, 72), 'mail-' + str(items))
                else:
                    player.auctioneer = native_guid
                    player.send(0x255, struct.pack('<Q', native_guid))
                    player.stay(.6)
                    require(player.hellos == [(native_guid, 2, 1)], 'No enabled Alliance auction hello')
                    self.attempt(player, 0x256, auction_packet(native_guid, 256, 2), (0, 0, 2), 'ordinary-owned-single-item-overcount-no-post')
                    for item in (269, 285):
                        self.attempt(player, 0x256, auction_packet(native_guid, item), (0, 0, 2), 'auction-bound-' + str(item))
        finally:
            self.offline(22)
            after = self.saved()
            save(output / (phase + '-after.json'), after)
            emit('after_select', phase=phase, snapshot=after)
            require(before == after, 'Phase changed persisted items/economics/mail/auction; preserve without repair')


def main(argv=None):
    global LOG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(PLAN, indent=2))
        return 0
    require(os.environ.get('WOWPILAGO_TEST_ACCOUNT_PASSWORD') == 'test-only' and
            os.environ.get('WOWPILAGO_DB_PASSWORD') == 'test-only', 'Explicit test credentials required')
    output = OUTPUT / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    output.mkdir(parents=True)
    import pymysql
    import verify_trade_runtime as trade
    import verify_merchant_runtime as merchant
    old_emit = trade.emit, merchant.emit
    trade.emit = merchant.emit = emit
    result = dict(event='FAIL', error='Not completed')
    with (output / 'run.jsonl').open('x') as LOG:
        try:
            evidence = probe_source()
            emit('pinned_source', **evidence, runtime=runtime_evidence(evidence))
            with pymysql.connect(host='127.0.0.1', port=13317, user='root', password='test-only',
                                 autocommit=True, cursorclass=pymysql.cursors.DictCursor,
                                 connect_timeout=5, read_timeout=15, write_timeout=15) as db:
                runner = TransferRunner(db)
                runner.preflight()
                runner.reuse()
                runner.reuse_control()
                pre = runner.saved()
                runner.prepare(pre)
                save(output / 'pre-setup.json', pre)
                emit('pre_setup_select', snapshot=pre)
                for phase in ('mail', 'auction'):
                    native_guid = runner.setup_phase(phase)
                    runner.phase(phase, native_guid, output)
                final = probe_source()
                emit('final_source', **final, runtime=runtime_evidence(final))
                result = dict(event='PASS', checks=PLAN['checks'], world_sha256=WORLD_HASH,
                              offline_fixture_guids=[13, 22, 23],
                              unchanged_phase_snapshots=True, completed_transfers=False,
                              boundary='mail control passed preceding validation only; AH hello and ordinary overcount refusal, no successful send/listing')
        except Exception as exc:
            result = dict(event='FAIL', error=str(exc), history='Preserved without repair/reset')
        emit(**result)
        save(output / 'summary.json', dict(result=result, run_sha256=digest((output / 'run.jsonl').read_bytes()), output=str(output)))
    LOG = None
    trade.emit, merchant.emit = old_emit
    return 0 if result['event'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
