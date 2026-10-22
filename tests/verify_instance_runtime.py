"""Preparation only by default: same level-1 peer 23, AP 286 vs one ordinary 756."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import json
import os
import struct
import sys
from unittest.mock import patch

import verify_transfer_runtime as transfer
import verify_trade_runtime as trade
import verify_merchant_runtime as merchant
from verify_runtime import SmokeClient, require, say_packet
from verify_merchant_runtime import equip_packet

OUTPUT = transfer.OUTPUT / 'instance'
PLAN = dict(network_without_run=False, player=23, authorized_guid=286, entry=756,
            setup='one GM13 .additem 756 1 on selected 23; exclusive reservation and exact persistent attestation',
            checks=['AP 286 native mainhand 15 at level 1',
                    'same-player ordinary 756 native required-level error 1, unchanged denial snapshot',
                    'no new authorization, proficiency, class, race, skill or economic changes'],
            requires='fresh parent release of all native matrix ownership, all offline, fixed-candidate transfer PASS first')


def auction_proof():
    paths = sorted(transfer.OUTPUT.glob('*/summary.json'), reverse=True)
    for path in paths:
        summary = json.loads(path.read_text())
        result = summary.get('result', {})
        if result.get('event') != 'PASS':
            continue
        data = (path.parent / 'run.jsonl').read_bytes()
        require(result.get('world_sha256') == transfer.WORLD_HASH
                and result.get('checks') == transfer.PLAN['checks']
                and summary.get('run_sha256') == transfer.digest(data), 'Invalid fixed auction proof')
        return dict(path=str(path), sha256=transfer.digest(path.read_bytes()))
    raise RuntimeError('Fixed-candidate auction PASS required before instance setup')


def ordinary_instance(snapshot):
    peer = snapshot['fixtures']['23']
    rows = [i for i in peer['items'] if i['itemEntry'] == 756 and i['guid'] != 286]
    require(len(rows) == 1, 'Need exactly one attested ordinary 756; never add a second')
    item = rows[0]
    require(item['owner_guid'] == 23 and item['count'] == 1 and item['flags'] == 0
            and item['duration'] == 0 and not any(map(int, item['enchantments'].split()))
            and item['guid'] not in {r['item_guid'] for r in peer['authorized']}
            and any(v['item'] == item['guid'] and v['bag'] == 0 and 23 <= v['slot'] < 39
                    for v in peer['inventory']), 'Ordinary copy must be owned, unequipped and unauthorized')
    return item


def level_denial(payload, ordinary):
    require(len(payload) == 22 and payload[0] == 1
            and struct.unpack_from('<Q', payload, 1)[0] == ((0x4000 << 48) | ordinary)
            and struct.unpack_from('<I', payload, 18)[0] == 24,
            'Expected native level error 1, actual ordinary GUID and required level 24')


class InstanceClient(transfer.TransferClient):
    def __init__(self, sock, authorize, guid):
        super().__init__(sock, authorize, guid)
        self.selected = None
        self.add_reserved = False
        self.ordinary = None
        self.errors = []

    def send(self, opcode, payload=b''):
        require(self.guid in (13, 23), 'Only GM13 and owned peer23')
        if opcode == 0x13D:
            require(self.guid == 13 and payload == struct.pack('<Q', 23), 'Only select 23')
            self.selected = 23
        elif opcode == 0x95:
            require(self.guid == 13 and self.selected == 23 and self.add_reserved
                    and payload == say_packet('.additem 756 1'), 'Only reserved ordinary setup on selected 23')
            self.add_reserved = False
        elif opcode == 0x10F:
            require(self.guid == 23 and payload in {equip_packet(i, 15) for i in (286, self.ordinary)
                                                  if i is not None}, 'Only own attested mainhand comparison')
        else:
            require(opcode in (0x1ED, 0x37, 0x3D, 0x1DC, 0x391, 0x4B), 'No commands, creation or transfers')
            if opcode == 0x3D:
                require(payload == struct.pack('<Q', self.guid), 'Wrong login GUID')
            if opcode in (0x37, 0x4B):
                require(not payload, 'Unexpected payload')
        transfer.emit('packet', guid=self.guid, direction='CMSG', opcode=hex(opcode), raw=payload.hex())
        SmokeClient.send(self, opcode, payload)

    def process(self, opcode, payload):
        if opcode == 0x112:
            require(bool(payload), 'Empty inventory failure')
            self.errors.append(payload)
            transfer.emit('inventory_error', guid=self.guid, raw=payload.hex(), code=payload[0])
        super().process(opcode, payload)


class InstanceRunner(transfer.TransferRunner):
    client_type = InstanceClient

    def saved(self):
        state = super().saved()
        state['peer_skills'] = self.query('SELECT * FROM acore_characters.character_skills WHERE guid=23 ORDER BY skill')
        state['peer_profile'] = self.query('SELECT guid,account,name,race,class,level FROM acore_characters.characters WHERE guid=23')
        state['entry_authorizations'] = self.query('SELECT * FROM acore_characters.mod_archipelago_authorized_item WHERE item_entry=756 ORDER BY item_guid')
        return state

    def facts(self, state):
        peer = state['fixtures']['23']
        require(state['peer_profile'] == [dict(guid=23, account=6, name='Apsgiylwpuwg', race=1, **{'class': 1}, level=1)],
                'Preserve owned level-1 human warrior profile')
        require(dict(guid=23, skill=172, value=1, max=5) in state['peer_skills'], 'Normal two-hand axe skill 1/5 required')
        require(any(r['item_guid'] == 286 and r['item_entry'] == 756 for r in peer['authorized'])
                and any(r['item_guid'] == 286 and r['item_entry'] == 756 for r in peer['purchases'])
                and any(i['guid'] == 286 and i['owner_guid'] == 23 and i['itemEntry'] == 756
                        and i['flags'] == 1 and i['count'] == 1 for i in peer['items']),
                'Existing purchased AP286 authorization required')
        rows = self.query('SELECT entry,class,subclass,RequiredLevel,RequiredSkill,RequiredSkillRank,InventoryType,MaxCount '
                          'FROM acore_world.item_template WHERE entry=756')
        require(len(rows) == 1 and all(rows[0][k] == v for k, v in
                dict(entry=756, **{'class': 2}, subclass=1, RequiredLevel=24, RequiredSkill=0,
                     RequiredSkillRank=0, InventoryType=17, MaxCount=0).items()), 'Nonunique level-24 two-hand axe template required')
        transfer.emit('instance_preconditions', template=rows, skills=state['peer_skills'], profile=state['peer_profile'])

    def setup_ordinary(self):
        before = self.saved()
        self.facts(before)
        attestation = OUTPUT / 'setup-attestation.json'
        if attestation.exists():
            proof = json.loads(attestation.read_text())
            item = ordinary_instance(before)
            require(proof['ordinary_item'] == item and proof['no_authorization'] is True
                    and proof['owner'] == 23 and proof['command'] == '.additem 756 1', 'Setup attestation mismatch')
            for name in ('setup-before.json', 'setup-after.json', 'setup-command.json'):
                require(transfer.digest((OUTPUT / name).read_bytes()) == proof['hashes'][name], 'Setup evidence changed')
            require(item['guid'] not in {r['item_guid'] for r in before['entry_authorizations']}, 'Ordinary gained authorization')
            transfer.emit('reuse_ordinary_setup', proof=proof)
            return item['guid']
        require([i['guid'] for i in before['fixtures']['23']['items'] if i['itemEntry'] == 756] == [286],
                'Unattested ordinary copy exists; preserve and stop')
        # Reserve before authentication. An interrupted setup requires parent inspection, never another add.
        with (OUTPUT / 'setup-reservation.json').open('x') as handle:
            json.dump(dict(owner=23, gm=13, command='.additem 756 1', no_authorization=True), handle)
        transfer.save(OUTPUT / 'setup-before.json', before)
        with self.login(13) as gm, self.login(23) as player:
            gm.send(0x13D, struct.pack('<Q', 23))
            gm.add_reserved = True
            messages = gm.command('.additem 756 1')
            player.stay(.6)
            transfer.save(OUTPUT / 'setup-command.json', dict(command='.additem 756 1', target=23, messages=messages))
        after = self.saved()
        transfer.save(OUTPUT / 'setup-after.json', after)
        item = ordinary_instance(after)
        require(item['guid'] not in {i['guid'] for i in before['fixtures']['23']['items']}, 'Ordinary GUID is not new')
        require(item['guid'] not in {r['item_guid'] for r in after['entry_authorizations']}, 'Ordinary was authorized')
        expected = json.loads(json.dumps(after, default=str))
        expected['fixtures']['23']['items'].remove(item)
        expected['fixtures']['23']['inventory'] = [v for v in expected['fixtures']['23']['inventory'] if v['item'] != item['guid']]
        require(expected == json.loads(json.dumps(before, default=str)), 'Setup changed more than one ordinary instance')
        proof = dict(owner=23, command='.additem 756 1', ordinary_item=item, no_authorization=True,
                     hashes={n: transfer.digest((OUTPUT / n).read_bytes()) for n in
                             ('setup-before.json', 'setup-after.json', 'setup-command.json')})
        with attestation.open('x') as handle:
            json.dump(proof, handle, indent=2)
        return item['guid']

    def compare(self, ordinary, output):
        before = self.saved()  # Baseline AFTER native setup.
        self.facts(before)
        require(ordinary_instance(before)['guid'] == ordinary, 'Wrong ordinary instance')
        require(dict(bag=0, slot=25, item=286) in before['fixtures']['23']['inventory']
                and dict(bag=0, slot=15, item=266) in before['fixtures']['23']['inventory'],
                'AP positive must start unequipped with original 49778 mainhand; no reset')
        transfer.save(output / 'equip-before.json', before)
        try:
            with self.login(23) as player:
                player.ordinary = ordinary
                player.send(0x10F, equip_packet(286, 15))
                player.stay(.6)
                require(not player.errors, 'AP286 native equip returned inventory error')
            equipped = self.saved()
            transfer.save(output / 'ap-equipped.json', equipped)
            expected = json.loads(json.dumps(before, default=str))
            inv = expected['fixtures']['23']['inventory']
            for row in inv:
                if row['item'] == 286:
                    row['slot'] = 15
                elif row['item'] == 266:
                    row['slot'] = 25
            inv.sort(key=lambda r: (r['bag'], r['slot']))
            require(json.loads(json.dumps(equipped, default=str)) == expected,
                    'AP286 equip must only swap original weapon to backpack naturally')
            with self.login(23) as player:
                player.ordinary = ordinary
                player.send(0x10F, equip_packet(ordinary, 15))
                player.stay(.6)
                require(len(player.errors) == 1, 'Exactly one native ordinary refusal required')
                level_denial(player.errors[0], ordinary)
            require(self.saved() == equipped, 'Ordinary denial mutated saved state')
        finally:
            self.offline(23)
            transfer.save(output / 'equip-after.json', self.saved())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(PLAN, indent=2))
        return 0
    evidence = transfer.probe_source()
    runtime = transfer.runtime_evidence(evidence)
    auction = auction_proof()
    require(os.environ.get('WOWPILAGO_TEST_ACCOUNT_PASSWORD') == 'test-only'
            and os.environ.get('WOWPILAGO_DB_PASSWORD') == 'test-only', 'Explicit test credentials required')
    output = OUTPUT / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    output.mkdir(parents=True)
    import pymysql
    result = dict(event='FAIL', history='Preserved without repair/reset')
    with (output / 'run.jsonl').open('x', buffering=1) as log, redirect_stdout(log), \
            patch.object(trade, 'emit', transfer.emit), patch.object(merchant, 'emit', transfer.emit):
        try:
            transfer.emit('pinned_source', **evidence, runtime=runtime, auction=auction)
            with pymysql.connect(host='127.0.0.1', port=13317, user='root', password='test-only', autocommit=True,
                                 cursorclass=pymysql.cursors.DictCursor, connect_timeout=5, read_timeout=15, write_timeout=15) as db:
                runner = InstanceRunner(db)
                runner.preflight()
                runner.reuse()
                runner.reuse_control()
                ordinary = runner.setup_ordinary()
                runner.compare(ordinary, output)
                runner.offline(13)
                runner.offline(22)
                final = transfer.probe_source()
                transfer.runtime_evidence(final)
                result = dict(event='PASS', ordinary_guid=ordinary, ap_guid=286, player=23,
                              checks=PLAN['checks'], offline_fixture_guids=[13, 22, 23])
        except Exception as exc:
            result['error'] = str(exc)
        transfer.emit(**result)
    transfer.save(output / 'summary.json', dict(result=result, run_sha256=transfer.digest((output / 'run.jsonl').read_bytes())))
    return 0 if result['event'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
