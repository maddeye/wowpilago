"""Bounded native travel checks. Synthetic AP ingress, never real-room proof.

Without --run this prints an offline plan. One fresh APV2F fixture only.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import struct
import sys
import time
from unittest.mock import patch

import verify_runtime as shared
from verify_runtime import Runner, SmokeClient, require, guard_account, manifest_fixture, selection_packet, LABEL
from verify_merchant_runtime import MerchantRunner, probe_source, SOURCE, WORLD_HASH
from verify_class_systems import DBC_DIR, items
from bridge.catalog import Catalog
from tools.validate_checks import DBC

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '.local/travel-live'
MOUNTS = (458, 23227, 32239)
PLAN = {'label': LABEL, 'network_without_run': False,
        'creates': 'one fresh APV2F SEC_PLAYER human warrior; source-proven reused TEST GM 13 only',
        'checks': ['online target TeleportTo denies expansions before native receipts and permits after',
                   'ordinary CMSG_CAST_SPELL ground mounts, pending permissions and level gates',
                   'Expert flight denied on map 0, allowed in Outland; Cold Weather in Northrend at 77'],
        'excluded': ['real AP room', 'GUI control', 'normal gameplay claim', 'all five training thresholds',
                     'SQL character writes', 'offline teleport as access proof', 'native rebuild']}


def emit(event, **values):
    print(json.dumps({'event': event, **values}, default=str, sort_keys=True), flush=True)


def packed_guid(data, offset=0):
    require(offset < len(data), 'Missing packed GUID mask')
    mask = data[offset]
    offset += 1
    guid = 0
    for index in range(8):
        if mask & (1 << index):
            require(offset < len(data), 'Truncated packed GUID')
            guid |= data[offset] << (index * 8)
            offset += 1
    return guid, offset


def cast_packet(spell, count):
    require(type(spell) is int and spell in (*MOUNTS, 32242) and type(count) is int and 0 <= count < 256,
            'Only bounded ordinary mount casts')
    return struct.pack('<BIBI', count, spell, 0, 0)  # flags 0; TARGET_FLAG_SELF 0


def spell_go(data):
    caster, offset = packed_guid(data)
    unit, offset = packed_guid(data, offset)
    require(len(data) >= offset + 13, 'Truncated SPELL_GO')
    count, spell = struct.unpack_from('<BI', data, offset)
    return caster, unit, count, spell


class TravelClient(SmokeClient):
    """Extend, rather than replace, the shared persistent ping and auth client."""
    def __init__(self, *args, **kwargs):
        self.world = None
        self.failures, self.casts, self.speeds = [], [], []
        super().__init__(*args, **kwargs)

    def send(self, opcode, payload=b''):
        emit('packet', direction='client', opcode=hex(opcode), raw=payload.hex())
        super().send(opcode, payload)

    def receive(self):
        opcode, payload = super().receive()
        emit('packet', direction='server', opcode=hex(opcode), raw=payload.hex())
        return opcode, payload

    def process(self, opcode, payload):
        if opcode in (0x236, 0x03E):  # LOGIN_VERIFY_WORLD, NEW_WORLD
            require(len(payload) == 20, 'Invalid world location')
            self.world = struct.unpack('<Iffff', payload)
            emit('world_location', location=self.world)
            if opcode == 0x03E:
                self.send(0x0DC)  # MSG_MOVE_WORLDPORT_ACK
        elif opcode == 0x0C7:  # server's near teleport: packed mover GUID + sequence + MovementInfo
            _, offset = packed_guid(payload)
            require(len(payload) >= offset + 30 and self.world is not None, 'Truncated near teleport')
            sequence, = struct.unpack_from('<I', payload, offset)
            self.world = (self.world[0], *struct.unpack_from('<ffff', payload, offset + 14))
            self.send(0x0C7, payload[:offset] + struct.pack('<II', sequence, 0))
        elif opcode == 0x130:
            require(len(payload) >= 6, 'Truncated CAST_FAILED')
            self.failures.append(struct.unpack_from('<BIB', payload))
            emit('cast_failure', count=self.failures[-1][0], spell=self.failures[-1][1], result=self.failures[-1][2])
        elif opcode == 0x132:
            self.casts.append(spell_go(payload))
            emit('spell_go', caster=self.casts[-1][0], unit=self.casts[-1][1],
                 count=self.casts[-1][2], spell=self.casts[-1][3])
        elif opcode in (0x0E2, 0x381):
            guid, offset = packed_guid(payload)
            require(len(payload) == offset + (9 if opcode == 0x0E2 else 8), 'Invalid forced speed packet')
            speed, = struct.unpack_from('<f', payload, len(payload) - 4)
            self.speeds.append((opcode, guid, speed))
            emit('native_speed', opcode=hex(opcode), guid=guid, speed=speed)
        super().process(opcode, payload)


def source_evidence():
    evidence = probe_source()
    files = {
        'src/server/game/Entities/Player/Player.cpp': ['OnPlayerCanAccessMap(this, mapid, &destination, false)'],
        'src/server/scripts/Commands/cs_tele.cpp': ['if (Player* target = player.GetConnectedPlayer())',
            'target->TeleportTo({ mapId, pos });', 'Player::SavePositionInDB'],
        'src/server/game/Handlers/MiscHandler.cpp': ['IsInAreaTriggerRadius', 'player->TeleportTo(at->target_mapId'],
        'src/server/game/Handlers/SpellHandler.cpp': ['recvPacket >> castCount >> spellId >> castFlags;', 'targets.Read(recvPacket, mover);'],
        'src/server/game/Handlers/MovementHandler.cpp': ['HandleMoveTeleportAck', 'SetSemaphoreTeleportNear(0)'],
        'src/server/game/Spells/Spell.cpp': ['WorldPacket data(SMSG_SPELL_GO', 'WorldPacket data(SMSG_CAST_FAILED'],
        'src/server/shared/DataStores/DBCStructure.h': ['EffectBasePoints', 'EffectApplyAuraName'],
    }
    for name, tokens in files.items():
        data = (SOURCE / name).read_bytes()
        require(all(t in data.decode() for t in tokens), 'Native layout changed: ' + name)
        evidence['hashes'][name] = hashlib.sha256(data).hexdigest()
    for name in ('APProgression.cpp', 'APProgression.h'):
        data = (ROOT / 'src' / name).read_bytes()
        require(data == (SOURCE / 'modules/mod-archipelago/src' / name).read_bytes(), 'Module changed: ' + name)
        evidence['hashes'][name] = hashlib.sha256(data).hexdigest()
    spells = DBC(DBC_DIR / 'Spell.dbc')
    evidence['dbc_spells'] = {str(i): list(spells.rows[i]) for i in MOUNTS}
    require(spells.rows[458][95:98] == (78, 32, 0) and spells.rows[458][81] == 59,
            '458 is not mounted +60%')
    require(spells.rows[23227][95:98] == (78, 32, 0) and spells.rows[23227][81] == 99,
            '23227 is not mounted +100%')
    require(spells.rows[32239][95:98] == (78, 207, 32), '32239 is not ordinary flying mount')
    evidence['dbc_sha256'] = hashlib.sha256((DBC_DIR / 'Spell.dbc').read_bytes()).hexdigest()
    return evidence


class TravelRunner(Runner):
    reuse_control = MerchantRunner.reuse_control

    def __init__(self, db):
        super().__init__(db, 'APV2F')
        self.created = False
        self.codes = []
        self.store = None
        self.guid = None
        self.checks = []
        self.level = 1
        self.count = 0

    @contextmanager
    def login(self, account, *, guid=None):
        require(account in ('APV2F', 'TEST'), 'Protected account')
        if guid is None:
            require(account == 'APV2F' and not self.created, 'Only one fresh APV2F fixture')
            row = self.account_row(account)
            guard_account(row, account)
            require(self.query('SELECT COUNT(*) AS n FROM acore_characters.characters WHERE account=%s',
                               (row['id'],))[0]['n'] < 10, 'No APV2F capacity')
            self.created = True
        else:
            require(guid in self.known and guid > 4 and (guid == 13 if account == 'TEST' else guid == self.guid),
                    'Not owned travel fixture/control')
        with super().login(account, guid=guid) as result:
            yield result

    def protected(self):
        result = {'characters': self.query('SELECT * FROM acore_characters.characters WHERE guid IN (1,2,3) ORDER BY guid')}
        for table in ('character_spell', 'character_talent', 'character_aura', 'character_inventory'):
            result[table] = self.query('SELECT * FROM acore_characters.' + table + ' WHERE guid IN (1,2,3) ORDER BY guid')
        return result

    def state(self, label):
        self.offline(self.guid)
        state = self.snapshot(self.guid, self.binding)
        state['location'] = self.character(self.guid)
        state['auras'] = self.query('SELECT * FROM acore_characters.character_aura WHERE guid=%s ORDER BY spell', (self.guid,))
        emit('durable_state', label=label, state=state)
        return state

    def queue(self, player, gm, *codes):
        require(self.store.receive(len(self.codes), items(codes)), 'Synthetic ingress rejected')
        self.codes.extend(codes)
        emit('fabricated_ingress', guid=self.guid, binding=self.binding, codes=codes, label=LABEL)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            rows = self.query('SELECT ap_item,applied FROM acore_characters.mod_archipelago_reward '
                              'WHERE binding_id=%s ORDER BY item_index', (self.binding,))
            if len(rows) == len(self.codes) and all(r['applied'] for r in rows):
                require([r['ap_item'] for r in rows] == self.codes, 'Wrong native receipts')
                player.stay(.4)
                return
            player.stay(.2)
            gm.stay(.05)
        raise RuntimeError('Native delivery timeout')

    def setup(self, gm, command):
        require(self.guid in self.known and self.character(self.guid)['online'] == 1, 'Setup requires owned ONLINE fixture')
        gm.send(0x13D, selection_packet(self.guid))
        emit('gm_command', target=self.guid, command=command, replies=gm.command(command))

    def advance(self, player, gm, target):
        require(self.level < target <= 80, 'Forward levels only')
        self.setup(gm, '.levelup ' + self.names[self.guid] + ' ' + str(target - self.level))
        self.level = target
        player.stay(.5)

    def teleport(self, player, gm, destination, expected):
        require(destination in ('Stormwind', 'HellfirePeninsula', 'BoreanTundra', 'Darnassus'), 'Unbounded destination')
        before = player.world
        self.setup(gm, '.tele name ' + self.names[self.guid] + ' ' + destination)
        for _ in range(10):
            player.stay(.2)
            gm.stay(.05)
        require(player.world is not None and player.world[0] == expected, 'Online target access differs: ' + destination)
        emit('online_teleport', destination=destination, before=before, after=player.world,
             expected_map=expected, proof='ONLINE TeleportTo plus ordinary client worldport ack, never offline SavePosition')
        self.checks.append('online access ' + destination + ' -> ' + str(expected))

    def cast(self, player, spell, *, error=None, speed=None):
        self.count += 1
        require(self.count < 256, 'Cast counter exhausted')
        player.send(0x136, struct.pack('<I', spell))
        player.stay(.2)
        player.casts.clear()
        player.failures.clear()
        player.speeds.clear()
        player.send(0x12E, cast_packet(spell, self.count))
        player.stay(4)
        failure = [f for f in player.failures if f[:2] == (self.count, spell)]
        success = [c for c in player.casts if c == (self.guid, self.guid, self.count, spell)]
        if error is not None:
            require(failure == [(self.count, spell, error)] and not success, 'Expected native mount refusal differs')
        else:
            require(success and not failure, 'No successful ordinary mount SPELL_GO')
            require(any(g == self.guid and abs(s - speed) < .02 for _, g, s in player.speeds), 'Native mounted speed differs')
        emit('mount_assertion', guid=self.guid, spell=spell, level=self.level, map=player.world[0],
             error=error, speed=speed, cast_count=self.count)
        self.checks.append('cast ' + str(spell) + (' denied ' + str(error) if error is not None else ' speed ' + str(speed)))

    def execute(self):
        from bridge.v2 import Store
        control = self.reuse_control()
        row = self.account_row('APV2F')
        guard_account(row, 'APV2F')
        require(self.query('SELECT COUNT(*) AS n FROM acore_characters.characters WHERE account=%s', (row['id'],))[0]['n'] == 0,
                'This bounded task requires unused APV2F, never create a second travel fixture')
        catalog = Catalog()
        seed = 'fabricated-travel-' + secrets.token_hex(12)
        raw = manifest_fixture(catalog, seed)
        (OUTPUT / 'manifest.json').write_text(json.dumps(raw, indent=2))
        with self.login('APV2F') as (_, self.guid):
            creation = dict(guid=self.guid, name=self.names[self.guid], account='APV2F', label=LABEL)
            (OUTPUT / 'creation.json').write_text(json.dumps(creation, indent=2))
            emit('fixture_created', **creation)
        require(self.offline(self.guid)['level'] == 1, 'Not fresh level 1')
        require(not self.query('SELECT id FROM acore_characters.mod_archipelago_binding WHERE character_guid=%s', (self.guid,)), 'Do not reset history')
        self.store = Store(dict(host='127.0.0.1', port=13317, user='root', database='acore_characters'), self.guid, catalog)
        self.binding = self.store.bind(seed, 0, 1, raw)
        self.store.status('disconnected')
        emit('binding', guid=self.guid, binding=self.binding, seed=seed, label=LABEL)
        with self.login('TEST', guid=control) as (gm, _):
            with self.login('APV2F', guid=self.guid) as (player, _):
                # Learn mounts only. Riding spells must come from native receipt reconciliation.
                for spell in MOUNTS:
                    self.setup(gm, '.learn ' + str(spell))
                self.teleport(player, gm, 'Stormwind', 0)
                self.teleport(player, gm, 'HellfirePeninsula', 0)
                self.teleport(player, gm, 'BoreanTundra', 0)
                self.queue(player, gm, *([919100001] * 7), 919100010, 919100011, 919100012, 919100014)
                self.cast(player, 458, error=107)
            pending = self.state('permissions pending at level 1')
            require(not {33388, 33391, 34090, 54197} & {r['spell'] for r in pending['spells']}, 'Premature riding training')
            with self.login('APV2F', guid=self.guid) as (player, _):
                self.advance(player, gm, 20)
                self.cast(player, 458, speed=11.2)
            ground = self.state('actual 60 percent ground mount')
            require(any(r['spell'] == 458 for r in ground['auras']), 'Ground mount aura not saved')
            with self.login('APV2F', guid=self.guid) as (player, _):
                player.send(0x136, struct.pack('<I', 458))
                player.stay(.3)
                self.cast(player, 23227, error=107)
                self.advance(player, gm, 40)
                self.cast(player, 23227, speed=14.0)
                player.send(0x136, struct.pack('<I', 23227))
                player.stay(.3)
                self.advance(player, gm, 60)
                self.cast(player, 32239, error=60)
                self.queue(player, gm, 919100002)
                self.teleport(player, gm, 'HellfirePeninsula', 530)
                self.cast(player, 32239, speed=17.5)
            flying = self.state('actual Outland Expert flight')
            require(any(r['spell'] == 32239 for r in flying['auras']), 'Flying mount aura not saved')
            with self.login('APV2F', guid=self.guid) as (player, _):
                player.send(0x136, struct.pack('<I', 32239))
                player.stay(.3)
                self.teleport(player, gm, 'BoreanTundra', 530)
                self.queue(player, gm, 919100003)
                self.teleport(player, gm, 'BoreanTundra', 571)
                self.cast(player, 32239, error=60)
                self.advance(player, gm, 77)
                self.cast(player, 32239, speed=17.5)
            north = self.state('Northrend Cold Weather at 77')
            require(north['location']['level'] == 77 and north['location']['map'] == 571
                    and any(r['spell'] == 54197 for r in north['spells'])
                    and any(r['spell'] == 32239 for r in north['auras']), 'Saved Northrend proof differs')
        self.offline(control)
        emit('PASS', guid=self.guid, binding=self.binding, gm_guid=control, checks=self.checks, label=LABEL)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(PLAN, indent=2))
        return 0
    require(os.environ.get('WOWPILAGO_TEST_ACCOUNT_PASSWORD') == 'test-only'
            and os.environ.get('WOWPILAGO_DB_PASSWORD') == 'test-only', 'Private test-only credentials required')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    require(not (OUTPUT / 'creation.json').exists(), 'One fixture already created; preserve it, do not rerun creation')
    emit('source_evidence', **source_evidence())
    import pymysql
    with pymysql.connect(host='127.0.0.1', port=13317, user='root', password='test-only', autocommit=True,
                         cursorclass=pymysql.cursors.DictCursor, connect_timeout=5, read_timeout=15, write_timeout=15) as db:
        runner = TravelRunner(db)
        before = runner.protected()
        (OUTPUT / 'before.json').write_text(json.dumps(before, default=str, indent=2))
        result = {'event': 'FAIL'}
        try:
            with patch.object(shared, 'SmokeClient', TravelClient):
                runner.execute()
            result = {'event': 'PASS'}
        except Exception as exc:
            result['error'] = str(exc)
            emit('FAIL', error=str(exc), completed_checks=runner.checks, preserved='all fixture/history; no native edits')
        finally:
            if runner.store is not None:
                runner.store.close()
            after = runner.protected()
            unchanged = before == after
            (OUTPUT / 'after.json').write_text(json.dumps(after, default=str, indent=2))
            if not unchanged:
                result = {'event': 'FAIL', 'error': 'Protected GUIDs 1..3 changed'}
            emit('protected_assertion', guids=[1, 2, 3], unchanged=unchanged, guid4='excluded: active legitimate journey')
            summary = dict(result=result, guid=runner.guid, checks=runner.checks, protected_unchanged=unchanged,
                           world_sha256=WORLD_HASH, label=LABEL)
            (OUTPUT / 'summary.json').write_text(json.dumps(summary, indent=2))
    return 0 if result['event'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
