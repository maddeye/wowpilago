"""Offline policy/packet checks. None authenticate or connect to a DB."""
import contextlib
from copy import deepcopy
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch

import verify_talent_switch_runtime as switch
from verify_runtime import MARKER
from tools.validate_checks import DBC
from verify_class_systems import DBC_DIR
from integration_inputs import require_inputs


# Literal native counter464 differs from DB spawn79788. Entry918 is 0x396.
RUNTIME_GUID = 0xf1300003960001d0
STATIC_DERIVED_GUID = 0xf1300003960137ac
WORLD = (0, -8752.3, 377.572, 101.139, 1.29154)
TRAINER_REPLY = [
    'Player selected NPC',
    'DB GUID: 79788, current GUID: GUID Full: 0xf1300003960001d0 Type: Creature Entry: 918  Low: 464.',
    'Current Entry: 918 of (918, 0, 0).',
    'DisplayID: 1372 (Native: 1372).', 'Faction: 12.', 'npcFlags: 51.',
    'Level: 50.', 'EquipmentId: 0 (Original: 0).',
    'Health (base): 6645. (max): 6645. (current): 6645.',
    'Unit Flags: 0.', 'Unit Flags 2: 2048.', 'Dynamic Flags: 0.',
    'Faction Template: 12.', 'SpawnTime: Full:7m10s Remain:0s',
    'Loot: 0 Pickpocket: 0 Skinning: 0', 'InstanceID: 0', 'Phasemask: 1',
    'Armor: 2966', 'Position: -8752.3 377.572 101.139.',
    'AIName:  ScriptName: ', '* is trainer (16)', '* is class trainer (32)',
    'MechanicImmuneMask: 0x0', 'SpellSchoolImmuneMask: 0',
]


# Literal messages from schema-reviewed-execution/setup-unresolved-5.json.
CAPTURED_PINFO = [
    '| Player  |cffffffff|Hplayer:Apsckmrzjjql|h[Apsckmrzjjql]|h|r (guid: GUID Full: 0x0000000000000023 Type: Player Low: 35)',
    '| Account: APV2C (ID: 4),',
    '',
    ' GMLevel: 0',
    '| AccountFlags:',
    '| Last Login: 2026-10-19 23:53:45 (Failed Logins: 0)',
    '| OS: Win - Latency: 0 ms',
    '| Registration Email: wowpilago-fixture@invalid - Email: wowpilago-fixture@invalid',
    '| Last IP: 172.19.0.1 (Locked: No)',
    '| Level: 50 (0/120900 XP (120900 XP left))',
    '| Race: Male Human, Rogue',
    '| Alive ?: Yes',
    '| Phase: 1',
    '| Money: 1001g0s0c',
    '| Map: Eastern Kingdoms, Zone: Stormwind City',
    '| Played time: 7m45s',
    '| Online for: 12s',
]


def observed():
    return switch.observe_trainer(TRAINER_REPLY, WORLD, WORLD)


def guarded_client(guid=35, trainer=None, *, funded=False):
    from unittest.mock import Mock
    c = object.__new__(switch.TalentClient)
    c.guid, c.trainer, c.funded = guid, trainer, funded
    c.wipe, c.allowed_gossip, c.gossip = None, None, None
    c.pending_respec = False
    c.hello_pending, c.trainer_contact = False, False
    c.used_commands, c.world = set(), WORLD
    c.selected_guid, c.teleport_serial = None, 0
    from collections import Counter
    c.ignored = Counter()
    c.gossip_serial = 0
    c.log, c.grant_check = Mock(), Mock()
    return c


FIXTURE_DIR = switch.OUTPUT / 'gossip-boundary-fix'
CAPTURE_HASH = '22af5390f0c5d1580dd032b6cf8dc5b9c262bba4f8bdd0ad9efbe76529978def'


def captured_root():
    """Actual historical root; preserve its GUID/wires and verify original bytes."""
    import hashlib
    require_inputs(FIXTURE_DIR / 'ACTUAL-funded-readonly-proof.json')
    raw = (FIXTURE_DIR / 'ACTUAL-funded-readonly-proof.json').read_bytes()
    switch.require(hashlib.sha256(raw).hexdigest() == CAPTURE_HASH, 'Captured root hash differs')
    return json.loads(raw)['gossip']


def encode_gossip(gossip, *, coded=0):
    raw = struct.pack('<QIII', gossip['guid'], gossip['menu'], gossip['title'], len(gossip['options']))
    for o in gossip['options']:
        raw += (struct.pack('<IBBI', o['wire'], o['icon'], coded, o['price'])
                + o['text'].encode() + b'\0' + o['box'].encode() + b'\0')
    return raw + bytes(4)


def gossip_packet(menu, purpose, guid=RUNTIME_GUID):
    """Synthetic selection-boundary packet with arbitrary wire39, never producer proof."""
    # Root labels come from the independent hash-verified capture, not the consumer.
    if purpose in ('dual', 'respec'):
        option = captured_root()['options'][{'dual': 2, 'respec': 1}[purpose]]
    else:
        # Synthetic/source-derived purchase: no actual purchase capture is claimed.
        option = dict(text='I wish to learn Dual Specialization.', price=10000000, icon=0,
                      box='Are you sure you wish to purchase a Dual Talent Specialization?')
    return encode_gossip(dict(guid=guid, menu=menu, title=14391 if menu == 10371 else 4835,
                             options=[option | dict(wire=39)]))


def model_root_packet(*, purchased=False):
    """Captured root projected to the model's observed GUID; dual disappears after purchase."""
    root = captured_root()
    root['guid'] = RUNTIME_GUID
    if purchased:
        root['options'] = [o for o in root['options'] if o['wire'] != 2]
    return encode_gossip(root)


@contextlib.contextmanager
def setup_transport(*, funded=False):
    """Real guarded Client framing/processing over deterministic in-memory sockets."""
    import tempfile
    from unittest.mock import Mock
    class Wire:
        def __init__(self):
            self.pending, self.sent = bytearray(), []
        def sendall(self, data):
            self.sent.append(data)
        def recv(self, size):
            data = bytes(self.pending[:size])
            del self.pending[:size]
            return data
        def packet(self, opcode, payload):
            self.pending.extend(struct.pack('>H', len(payload)+2) + struct.pack('<H', opcode) + payload)
        def message(self, text):
            raw = text.encode() + b'\0'
            self.packet(0x96, struct.pack('<BIQIQI', 0, 0, 0, 0, 0, len(raw)) + raw + b'\0')
    with tempfile.TemporaryDirectory() as tmp:
        journal = switch.Journal(Path(tmp))
        gm = switch.TalentClient(Wire(), Mock(), 13, journal, Mock(), funded=funded)
        player = switch.TalentClient(Wire(), Mock(), 35, journal, Mock(), funded=funded)
        gm.world = player.world = WORLD
        gm.next_ping = player.next_ping = 1000
        runner = object.__new__(switch.TalentRunner)
        runner.journal = journal
        clock, scheduled = [0.0], []
        def poll(sockets, *args):
            clock[0] += .1
            for when, action in list(scheduled):
                if when <= clock[0]:
                    scheduled.remove((when, action))
                    action()
            return [s for s in sockets if s.pending], [], []
        with patch.object(switch.time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(switch.select, 'select', side_effect=poll):
            try:
                yield runner, gm, player, scheduled, clock, Path(tmp)
            finally:
                gm.packet_log.close()
                player.packet_log.close()


class TalentSwitchTests(unittest.TestCase):
    def test_delayed_money_confirmation_and_live_readback_drive_both_clients(self):
        with setup_transport() as (r, gm, player, events, clock, directory):
            gm.send(0x13D, struct.pack('<Q', 35))
            events.extend([(.2, lambda: player.sock.packet(0x390, struct.pack('<I', 7))),
                           (.8, lambda: gm.sock.message(switch.MONEY_SUCCESS))])
            r.setup_command(gm, player, switch.MONEY_COMMAND, switch.money_confirmation)
            self.assertGreater(clock[0], .5)
            self.assertTrue(any(struct.unpack_from('<I', raw, 2)[0] == 0x391
                                for raw in player.sock.sent))
            events.append((1.6, lambda: [gm.sock.message(m) for m in
                [switch.PINFO_HEADER, '¦ Money: 1001g0s0c', '¦ Online for: 1s']]))
            r.setup_command(gm, player, switch.MONEY_INFO, switch.money_readback)
            self.assertGreater(clock[0], 1.5)
            self.assertGreater(player.grant_check.call_count, 5)
            self.assertEqual(sum(raw[6:] == switch.say_packet(switch.MONEY_COMMAND)
                                 for raw in gm.sock.sent), 1)
            self.assertFalse(list(directory.glob('setup-unresolved*')))

    def test_money_confirmation_failures_never_repeat_and_record_before_cleanup(self):
        for reply in (None, 'No character selected.', 'You have low security level for this.',
                      switch.MONEY_SUCCESS.replace('Apsckmrzjjql', 'Otheractor'),
                      switch.MONEY_SUCCESS.replace('10010000', '10010001'),
                      'Player not found!'):
            with self.subTest(reply=reply), setup_transport() as (r, gm, player, events, clock, directory):
                gm.send(0x13D, struct.pack('<Q', 35))
                if reply is not None:
                    events.append((.8, lambda: gm.sock.message(reply)))
                with self.assertRaises(RuntimeError):
                    r.setup_command(gm, player, switch.MONEY_COMMAND, switch.money_confirmation)
                self.assertTrue(list(directory.glob('setup-unresolved*')))
                with self.assertRaises(RuntimeError):
                    gm.send(0x95, switch.say_packet(switch.MONEY_COMMAND))
                self.assertEqual(sum(raw[6:] == switch.say_packet(switch.MONEY_COMMAND)
                                     for raw in gm.sock.sent), 1)

    def test_readback_rejects_absent_offline_other_actor_wrong_money(self):
        good = [switch.PINFO_HEADER, '¦ Money: 1001g0s0c', '¦ Online for: 1s']
        self.assertTrue(switch.money_readback(good))
        for messages in ([], good[:2], good[1:]):
            self.assertFalse(switch.money_readback(messages))
        for messages in ([good[0].replace('Player  ', 'Player (offline) '), *good[1:]],
                         [good[0].replace('35)', '13)'), *good[1:]],
                         [good[0].replace('Apsckmrzjjql', 'Otheractor'), *good[1:]],
                         [good[0], '¦ Money: 1000g0s0c', good[2]]):
            with self.assertRaises(RuntimeError):
                switch.money_readback(messages)

    def test_actual_captured_pinfo_accepts_only_leading_separator_difference(self):
        original = deepcopy(CAPTURED_PINFO)
        self.assertTrue(switch.money_readback(CAPTURED_PINFO))
        self.assertEqual(CAPTURED_PINFO, original)
        canonical = ['¦ ' + m[2:] if m.startswith('| ') else m for m in CAPTURED_PINFO]
        self.assertTrue(switch.money_readback(canonical))
        self.assertIn(switch.PLAYER_LINK, canonical[0])
        for old, new in (('Low: 35)', 'Low: 13)'),
                         ('0000000000000023', '000000000000000d'),
                         ('Apsckmrzjjql', 'Otheractor'),
                         ('1001g0s0c', '1000g0s0c'),
                         ('Player  ', 'Player (offline) '),
                         ('|Hplayer:', '¦Hplayer:')):
            with self.subTest(new=new), self.assertRaises(RuntimeError):
                switch.money_readback([m.replace(old, new) for m in CAPTURED_PINFO])
        self.assertFalse(switch.money_readback(CAPTURED_PINFO[:-1]))
        self.assertFalse(switch.money_readback([m.replace('| Online for:', '| Offline for:')
                                               for m in CAPTURED_PINFO]))
        self.assertFalse(switch.money_readback([' ' + m for m in CAPTURED_PINFO]))

    def test_captured_ascii_pinfo_completes_real_guarded_setup_transport(self):
        with setup_transport() as (r, gm, player, events, clock, directory):
            gm.send(0x13D, struct.pack('<Q', 35))
            events.append((.2, lambda: gm.sock.message(switch.MONEY_SUCCESS)))
            r.setup_command(gm, player, switch.MONEY_COMMAND, switch.money_confirmation)
            events.append((.8, lambda: [gm.sock.message(m) for m in CAPTURED_PINFO]))
            r.setup_command(gm, player, switch.MONEY_INFO, switch.money_readback)
            self.assertFalse(list(directory.glob('setup-unresolved*')))

    def test_delayed_trainer_reply_is_complete_before_observation(self):
        with setup_transport() as (r, gm, player, events, clock, directory):
            gm.used_commands = {switch.say_packet(switch.GO), switch.say_packet(switch.SUMMON)}
            events.append((.8, lambda: [gm.sock.message(m) for m in TRAINER_REPLY[:-1]]))
            events.append((1.2, lambda: gm.sock.message(TRAINER_REPLY[-1])))
            messages = r.setup_command(gm, player, switch.TRAINER_INFO,
                lambda ms: TRAINER_REPLY[-1] in ms)
            self.assertGreaterEqual(clock[0], 1.2)
            self.assertEqual(switch.observe_trainer(messages, gm.world, player.world), observed())

    def test_delayed_teleports_require_fresh_ack_and_pump_both_clients(self):
        with setup_transport() as (r, gm, player, events, clock, directory):
            # At destination already is not completion of this invocation.
            serial = gm.teleport_serial
            events.append((.8, lambda: gm.sock.packet(0x3E, struct.pack('<Iffff', *WORLD))))
            r.setup_command(gm, player, switch.GO,
                lambda ms: gm.teleport_serial > serial and switch.at_trainer(gm.world))
            self.assertGreater(clock[0], .5)
            serial = player.teleport_serial
            events.append((1.6, lambda: gm.sock.message('You are summoning ' + switch.PLAYER_LINK + '.')))
            events.append((2.0, lambda: player.sock.packet(0x3E, struct.pack('<Iffff', *WORLD))))
            r.setup_command(gm, player, switch.SUMMON, lambda ms:
                ms == ['You are summoning ' + switch.PLAYER_LINK + '.']
                and player.teleport_serial > serial and switch.at_trainer(player.world))
            self.assertGreaterEqual(clock[0], 2.0)
            for client in (gm, player):
                self.assertTrue(any(struct.unpack_from('<I', raw, 2)[0] == 0xDC
                                    for raw in client.sock.sent))

    def test_readback_failure_after_one_money_send_preserves_unresolved(self):
        for replies in ([], [switch.PINFO_HEADER, '¦ Money: 1001g0s0c'],
                        [switch.PINFO_HEADER.replace('Player  ', 'Player  (offline)'),
                         '¦ Money: 1001g0s0c'],
                        [switch.PINFO_HEADER, '¦ Money: 0g0s0c', '¦ Online for: 1s'],
                        ['No character selected.']):
            with self.subTest(replies=replies), setup_transport() as (r, gm, player, events, clock, directory):
                gm.send(0x13D, struct.pack('<Q', 35))
                events.append((.8, lambda: gm.sock.message(switch.MONEY_SUCCESS)))
                r.setup_command(gm, player, switch.MONEY_COMMAND, switch.money_confirmation)
                events.append((1.6, lambda: [gm.sock.message(m) for m in replies]))
                with self.assertRaises(RuntimeError):
                    r.setup_command(gm, player, switch.MONEY_INFO, switch.money_readback)
                records = list(directory.glob('setup-unresolved*'))
                self.assertEqual(len(records), 1)
                self.assertEqual(json.loads(records[0].read_text())['command'], switch.MONEY_INFO)
                self.assertEqual(sum(raw[6:] == switch.say_packet(switch.MONEY_COMMAND)
                                     for raw in gm.sock.sent), 1)

    def test_offline_summon_is_terminal_without_waiting_for_deadline(self):
        with setup_transport() as (r, gm, player, events, clock, directory):
            events.append((.8, lambda: gm.sock.message('You are summoning ' + switch.PLAYER_LINK + ' (offline).')))
            with self.assertRaisesRegex(RuntimeError, 'refused'):
                r.setup_command(gm, player, switch.SUMMON, lambda ms: False)
            self.assertLess(clock[0], 2)

    def test_money_requires_selection_and_readback_is_finite(self):
        with setup_transport() as (r, gm, player, events, clock, directory):
            for command in (switch.MONEY_COMMAND, switch.MONEY_INFO, '.pinfo Otheractor', '.modify money 1'):
                with self.assertRaises(RuntimeError):
                    gm.send(0x95, switch.say_packet(command))
            self.assertEqual(gm.sock.sent, [])

    def test_paired_wait_rechecks_grants_before_processing(self):
        with setup_transport() as (r, gm, player, events, clock, directory):
            def expire():
                player.grant_check.side_effect = RuntimeError('expired')
                player.sock.packet(0x390, struct.pack('<I', 7))
            events.append((.8, expire))
            with self.assertRaisesRegex(RuntimeError, 'expired'):
                r.setup_command(gm, player, switch.GO, lambda ms: False)
            self.assertEqual(player.sock.sent, [])
            self.assertTrue(list(directory.glob('setup-unresolved*')))

    def test_driver_timestamps_match_archive_without_ignoring_changes(self):
        require_inputs(switch.BIRTH / 'replay.json', switch.BIRTH / 'manifest.json')
        replay = json.loads((switch.BIRTH / 'replay.json').read_text())
        manifest = json.loads((switch.BIRTH / 'manifest.json').read_text())
        binding = deepcopy(replay['binding'][0])
        binding['created_at'] = datetime.fromisoformat(binding['created_at'])
        switch.binding_guard(binding, replay['binding'][0], manifest)
        binding['created_at'] += timedelta(seconds=1)
        with self.assertRaisesRegex(RuntimeError, 'Binding changed'):
            switch.binding_guard(binding, replay['binding'][0], manifest)
        rows = deepcopy(replay['receipts'])
        for row in rows:
            for field in ('received_at', 'applied_at'):
                row[field] = datetime.fromisoformat(row[field])
        switch.receipt_guard(rows, replay['receipts'], applied=False)
        rows[0]['applied_at'] += timedelta(seconds=1)
        with self.assertRaisesRegex(RuntimeError, 'Old receipt prefix changed'):
            switch.receipt_guard(rows, replay['receipts'], applied=False)

    def test_default_constant_plan_without_observations(self):
        with patch.object(switch, 'source_evidence', side_effect=AssertionError('source read')), \
                patch.object(Path, 'read_text', side_effect=AssertionError('file read')), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(switch.main([]), 0)
        self.assertEqual(json.loads(out.getvalue()), switch.PLAN)
        self.assertTrue(switch.PLAN['live_executor'])

    def test_run_without_grant_rejects_before_observation(self):
        result = subprocess.run([sys.executable, str(Path(switch.__file__)), '--run'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--run requires parent --grant and --owners', result.stderr)
        with patch.object(switch, 'source_evidence', side_effect=AssertionError('read')), \
                patch.object(switch, 'run', side_effect=AssertionError('executor')):
            with self.assertRaisesRegex(RuntimeError, 'requires parent'):
                switch.main(['--run'])

    def test_production_earned_and_active_spec_masks(self):
        rows = [dict(spell=13792, specMask=1), dict(spell=14164, specMask=2)]
        ranks = {13792: 2, 14164: 2}
        self.assertEqual((switch.earned(0), switch.earned(1)), (33, 34))
        self.assertEqual(switch.free_points(0, 0, rows, ranks), 30)
        self.assertEqual(switch.free_points(0, 1, rows, ranks), 30)
        self.assertEqual(switch.free_points(1, 1, rows, ranks), 31)
        self.assertEqual(switch.free_points(1, 0, rows, ranks), 31)
        self.assertEqual(switch.free_points(1, 0, rows[1:], ranks), 34)
        self.assertEqual(switch.free_points(1, 1, rows[1:], ranks), 31)
        self.assertEqual(switch.free_points(1, 0, [dict(spell=13792, specMask=3)], ranks), 31)
        for active in (-1, 2, True):
            with self.assertRaises(RuntimeError):
                switch.free_points(0, active, rows, ranks)
        with self.assertRaises(RuntimeError):
            switch.free_points(0, 0, [dict(spell=13792, specMask=255)], ranks)

    def test_literal_native_packets_and_invalid_operations(self):
        self.assertEqual(switch.native_packet('learn', 2), (0x251, bytes.fromhex('cb00000002000000')))
        self.assertEqual(switch.native_packet('switch', 1), (0x12E, bytes.fromhex('009cf800000000000000')))
        self.assertEqual(switch.native_packet('wipe', RUNTIME_GUID),
                         (0x2AA, bytes.fromhex('d0010096030030f1')))
        for op, value in [('learn', 3), ('learn', True), ('switch', 63706), ('switch', True),
                          ('wipe', 35), ('send', 0x251), ('command', '.reset talents'),
                          ('switch', 63680)]:
            with self.assertRaises(RuntimeError):
                switch.native_packet(op, value)

    def test_direct_dbc_row_and_switch_effects(self):
        require_inputs(*(DBC_DIR / (n + '.dbc') for n in ('Talent', 'TalentTab', 'Spell')))
        talents, tabs, spells = [DBC(DBC_DIR / (n + '.dbc')) for n in ('Talent', 'TalentTab', 'Spell')]
        row = talents.rows[203]
        self.assertEqual(row[2], 0)
        self.assertEqual(talents.rows[1827][1:3], (181, 1))
        self.assertEqual(switch.native_packet('tier-denial'), (0x251, bytes.fromhex('2307000000000000')))
        self.assertEqual(row[4:9], (13741, 13793, 13792, 0, 0))
        self.assertEqual(tabs.rows[row[1]][20], 8)
        self.assertEqual(spells.rows[63680][116:119], (63645, 63644, 0))
        self.assertEqual(spells.rows[63624][71], 161)
        for spell, spec in ((63645, 0), (63644, 1)):
            self.assertEqual(spells.rows[spell][71], 162)
            self.assertEqual(spells.rows[spell][80], spec)
        self.assertEqual(switch.earned(12), 41)  # Why Warrior12 would hide the reservation bug.

    def test_typed_owned_first_player_login_not_known_guid_bypass(self):
        require_inputs(switch.BIRTH / 'creation.json', switch.BIRTH / 'first-login-authorized.json')
        birth = json.loads((switch.BIRTH / 'creation.json').read_text())
        first = json.loads((switch.BIRTH / 'first-login-authorized.json').read_text())
        character = dict(guid=35, account=4, name=birth['name'], race=1, level=50, online=0)
        character['class'] = 4
        account = dict(id=4, username='APV2C', email=MARKER, security=0, online=0)
        self.assertEqual(switch.owned_identity(character, account, birth, first), birth['profile'])
        for change in (dict(guid=4), dict(guid=12), dict(guid=40), dict(account=1),
                       dict(race=2), {'class': 1}, dict(name='Other'), dict(level=49), dict(online=1)):
            with self.assertRaises(RuntimeError):
                switch.owned_identity(character | change, account, birth, first)
        for change in (dict(username='APV2A'), dict(security=3), dict(id=True), dict(online=1)):
            with self.assertRaises(RuntimeError):
                switch.owned_identity(character, account | change, birth, first)

    def test_exact_binding_full_manifest_and_preserved_prefix(self):
        require_inputs(switch.BIRTH / 'replay.json', switch.BIRTH / 'manifest.json')
        replay = json.loads((switch.BIRTH / 'replay.json').read_text())
        raw = json.loads((switch.BIRTH / 'manifest.json').read_text())
        binding = replay['binding'][0]
        switch.binding_guard(binding | dict(status='disconnected'), binding, raw)
        for change in (dict(character_guid=12), dict(seed_name='other'), dict(character_account=1)):
            with self.assertRaises(RuntimeError):
                switch.binding_guard(binding | change, binding, raw)
        prefix = replay['receipts']
        switch.receipt_guard(prefix, prefix, applied=False)
        tail = dict(binding_id=25, item_index=len(prefix), ap_item=switch.UNLOCK,
                    kind='talent', applied=1, applied_value=1)
        after = prefix + [tail]
        switch.receipt_guard(after, prefix, applied=True)
        switch.receipt_guard(deepcopy(after), prefix, applied=True)  # Same replay must not append.
        for wrong in (after + [tail], prefix, prefix + [tail | dict(applied=0)],
                      prefix + [tail | dict(ap_item=919100001)]):
            with self.assertRaises(RuntimeError):
                switch.receipt_guard(wrong, prefix, applied=True)
        damaged = deepcopy(after)
        damaged[0]['applied'] = 0
        with self.assertRaises(RuntimeError):
            switch.receipt_guard(damaged, prefix, applied=True)

    def test_money_once_target_and_failure_burn(self):
        reservation = switch.SetupReservation()
        with self.assertRaises(RuntimeError):
            reservation.money_command(35)
        reservation.reserve()
        with self.assertRaises(RuntimeError):
            reservation.money_command(12)
        self.assertEqual(reservation.money_command(35), '.modify money 10010000')
        for action in (reservation.reserve, lambda: reservation.money_command(35)):
            with self.assertRaises(RuntimeError):
                action()

    def test_parent_release_ttl_hashes_and_all_current_owners(self):
        hashes = dict(world='test-only-not-a-grant')
        release = dict(parent_authorized=True, purpose='talent-switch', guids=[13, 35],
                       creation_limit=0, money_setup_copper=switch.MONEY, hashes=hashes,
                       setup_readback=switch.MONEY_INFO,
                       issued_at=100, expires_at=1900, released_owners=['AHbt62', 'parent'])
        def check(row, now=101):
            switch.release_guard(row, now=now, expected_hashes=hashes,
                                 current_owners=['AHbt62', 'parent'])
        check(release)
        for change in (dict(parent_authorized=False), dict(creation_limit=1), dict(guids=[13, 12]),
                       dict(expires_at=1901), dict(issued_at=102), dict(released_owners=['parent']),
                       dict(hashes={}), dict(money_setup_copper=10000000), dict(setup_readback='')):
            with self.assertRaises(RuntimeError):
                check(release | change)
        with self.assertRaises(RuntimeError):
            check(release, now=1900)


class FundedContinuationTests(unittest.TestCase):
    def grant(self):
        return dict(parent_authorized=True, purpose='talent-switch-funded', guids=[13, 35],
                    creation_limit=0, money_setup_copper=0, hashes={'offline': 'model'},
                    readonly_commands=[switch.TRAINER_INFO, switch.MONEY_INFO],
                    issued_at=100, expires_at=1900, released_owners=['parent', 'owner'],
                    prior_funding_attested=True, prior_funding_sha256=switch.PRIOR_FUNDING_HASHES)

    def test_missing_funded_grant_and_cli_escape_hatches_observe_nothing(self):
        with patch.object(switch, 'source_evidence', side_effect=AssertionError('source observation')), \
                patch.object(Path, 'read_text', side_effect=AssertionError('file observation')), \
                patch.object(switch, 'runtime_guard', side_effect=AssertionError('runtime')):
            for args in (['--continue-funded'], ['--continue-funded', '--grant', '/unused']):
                with self.assertRaisesRegex(RuntimeError, 'requires parent'):
                    switch.main(args)
            for flag in ('--resume', '--phase', '--output'):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    switch.main(['--continue-funded', flag, 'unused'])

    def test_funded_grant_exact_scope_hashes_owners_and_freshness(self):
        release = self.grant()
        check = lambda r: switch.release_guard(r, now=101, expected_hashes={'offline': 'model'},
                                               current_owners=['parent', 'owner'], funded=True)
        check(release)
        for change in (dict(purpose='talent-switch'), dict(guids=[35]), dict(guids=[13, 4]),
                       dict(creation_limit=True), dict(money_setup_copper=switch.MONEY),
                       dict(money_setup_copper=False), dict(readonly_commands=[switch.TRAINER_INFO]),
                       dict(readonly_commands=[switch.TRAINER_INFO, switch.MONEY_INFO, switch.GO]),
                       dict(prior_funding_attested=False), dict(prior_funding_sha256={}),
                       dict(hashes={}), dict(issued_at=102), dict(expires_at=101),
                       dict(expires_at=1901), dict(released_owners=['parent'])):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                check(release | change)

    def test_invalid_external_grant_denied_before_source_process_or_runtime_observation(self):
        import tempfile
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            grant, owners = Path(tmp) / 'grant.json', Path(tmp) / 'owners.json'
            owners.write_text(json.dumps(dict(purpose='current-native-owners', owners=['parent', 'owner'],
                                             all_released=True, no_other_runners=True, observed_at=100)))
            base = self.grant() | dict(release_id='offline-only', owners_sha256=hashlib.sha256(owners.read_bytes()).hexdigest())
            with patch.object(switch.time, 'time', return_value=101), \
                    patch.object(switch, 'source_evidence', side_effect=AssertionError('source')), \
                    patch.object(subprocess, 'check_output', side_effect=AssertionError('process')), \
                    patch.object(switch, 'runtime_guard', side_effect=AssertionError('runtime')):
                for change in (dict(parent_authorized=False), dict(owners_sha256='bad'),
                               dict(prior_funding_attested=False), dict(expires_at=101)):
                    grant.write_text(json.dumps(base | change))
                    with self.assertRaises(RuntimeError):
                        switch.run(grant, owners, funded=True)

    def test_archived_funding_is_verified_without_process_continuity(self):
        require_inputs(*(switch.ROOT / p for p in switch.PRIOR_FUNDING_HASHES))
        data, attestation = switch.prior_funding()
        self.assertEqual(len(data), 122)
        self.assertEqual(attestation['hashes'], switch.PRIOR_FUNDING_HASHES)
        self.assertTrue(attestation['old_trainer_guid_is_not_current_authority'])
        self.assertEqual(switch.AUTOMATIC_WORLDSTATE_KEYS, {3781})
        self.assertEqual(attestation['historical_only']['zone_check']['location_id'], 919701519)

    def test_tampered_or_wrong_prior_artifacts_fail_closed(self):
        require_inputs(*(switch.ROOT / p for p in switch.PRIOR_FUNDING_HASHES))
        pins = switch.PRIOR_FUNDING_HASHES
        for path in pins:
            with self.subTest(path=path), patch.object(switch, 'PRIOR_FUNDING_HASHES', pins | {path: '0'*64}):
                with self.assertRaisesRegex(RuntimeError, 'Preserved funding artifact changed'):
                    switch.prior_funding()

    def test_pristine_funded_baseline_rejects_cash_talents_unlocks_and_spec_staging(self):
        require_inputs(*(switch.ROOT / p for p in switch.PRIOR_FUNDING_HASHES))
        base, _ = switch.prior_funding()
        switch.pristine_funded(base)
        mutations = []
        for key, value in (('money', 0), ('money', switch.MONEY+1), ('xp', 1),
                           ('talentGroupsCount', 2), ('activeTalentGroup', 1), ('resettalents_cost', 10000),
                           ('position_x', 0), ('instance_id', 1)):
            row = deepcopy(base)
            next(r for r in row['characters'] if r['guid'] == 35)[key] = value
            mutations.append(row)
        row = deepcopy(base)
        row['character_talent'].append(dict(guid=35, spell=13741, specMask=1))
        mutations.append(row)
        row = deepcopy(base)
        next(r for r in row['mod_archipelago_progress'] if r['binding_id'] == 25)['talent_unlocks'] = 1
        mutations.append(row)
        for row in mutations:
            with self.assertRaises(RuntimeError):
                switch.pristine_funded(row)

    def test_funded_continuity_keeps_all_raw_tables_and_protected_state(self):
        require_inputs(*(switch.ROOT / p for p in switch.PRIOR_FUNDING_HASHES))
        base, _ = switch.prior_funding()
        original = deepcopy(base)
        after = deepcopy(base)
        next(r for r in after['worldstates'] if r['entry'] == 3781)['value'] += 1
        switch.funded_continuity(base, after)
        for table, key, value in (('characters', 'xp', 1), ('mod_archipelago_check', 'acknowledged', 1),
                                  ('mod_archipelago_reward', 'applied', 0), ('character_inventory', 'item', -1)):
            wrong = deepcopy(after)
            wrong[table][0][key] = value if wrong[table][0].get(key) != value else value + 2
            with self.assertRaises(RuntimeError):
                switch.funded_continuity(base, wrong)
        for key in (3801, 4024):
            wrong = deepcopy(after)
            next(r for r in wrong['worldstates'] if r['entry'] == key)['value'] += 1
            with self.assertRaisesRegex(RuntimeError, 'Protected worldstate'):
                switch.funded_continuity(base, wrong)
        next(r for r in after['characters'] if r['guid'] == 13)['totaltime'] += 1
        with self.assertRaises(RuntimeError):
            switch.funded_continuity(base, after)
        switch.funded_continuity(base, after, login_bookkeeping=True)
        self.assertEqual(base, original)

    def test_funded_real_clients_reject_every_write_command_selection_and_teleport(self):
        with setup_transport(funded=True) as (_, gm, player, _, _, _):
            for client in (gm, player):
                client.selected_guid = 35  # Even fabricated old setup state cannot grant writes.
                client.used_commands = {switch.say_packet(switch.GO), switch.say_packet(switch.SUMMON),
                                        switch.say_packet(switch.MONEY_COMMAND)}
                client.teleport_ack = b'fake-ack'
                for opcode, payload in [(0x95, switch.say_packet(cmd)) for cmd in
                        (switch.GO, switch.SUMMON, switch.MONEY_COMMAND, '.modify money 1', '.reset talents',
                         '.npc info 918', '.pinfo Otheractor')] + [
                        (0x13D, struct.pack('<Q', 35)), (0xC7, b'fake-ack'), (0xDC, b''), (0x36, b'')]:
                    with self.subTest(opcode=opcode, payload=payload), self.assertRaises(RuntimeError):
                        client.send(opcode, payload)
                self.assertEqual(client.sock.sent, [])
            for command in (switch.TRAINER_INFO, switch.MONEY_INFO):
                with self.assertRaises(RuntimeError):
                    player.send(0x95, switch.say_packet(command))

    def test_funded_exact_readonly_commands_once_with_paired_real_transport(self):
        with setup_transport(funded=True) as (r, gm, player, events, clock, directory):
            with self.assertRaises(RuntimeError):
                gm.send(0x95, switch.say_packet(switch.MONEY_INFO))
            fresh = [m.replace('0001d0', '003039').replace('Low: 464', 'Low: 12345') for m in TRAINER_REPLY]
            events.append((.8, lambda: [gm.sock.message(m) for m in fresh]))
            messages = r.setup_command(gm, player, switch.TRAINER_INFO, lambda ms: fresh[-1] in ms)
            gm.trainer = player.trainer = switch.observe_trainer(messages, gm.world, player.world)
            self.assertEqual(gm.trainer.guid, 0xf130000396003039)
            events.append((1.6, lambda: [gm.sock.message(m) for m in CAPTURED_PINFO]))
            r.setup_command(gm, player, switch.MONEY_INFO, switch.money_readback)
            for command in (switch.TRAINER_INFO, switch.MONEY_INFO):
                with self.assertRaises(RuntimeError):
                    gm.send(0x95, switch.say_packet(command))
            for guid in (RUNTIME_GUID, STATIC_DERIVED_GUID):
                with self.assertRaises(RuntimeError):
                    player.send(0x17B, struct.pack('<Q', guid))
            player.send(0x17B, struct.pack('<Q', gm.trainer.guid))
            self.assertGreater(clock[0], 1.5)
            self.assertEqual(len(gm.sock.sent), 2)
            self.assertFalse(list(directory.glob('money*')))

    def test_funded_journal_has_no_money_marker_and_no_attempt_retry(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            journal = switch.Journal(Path(tmp), funded=True)
            with self.assertRaises(RuntimeError):
                journal.record('money-burned', {})
            journal.record('attempt', dict(money_reserved=0))
            with self.assertRaises(FileExistsError):
                journal.record('attempt', {})
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ['attempt.json'])
        self.assertEqual(switch.FUNDED_JOURNAL, switch.OUTPUT / 'funded-continuation')

    def test_real_preflight_uses_exact_funded_baseline_and_original_manifest(self):
        require_inputs(*(switch.ROOT / p for p in switch.PRIOR_FUNDING_HASHES),
                       switch.BIRTH / 'replay.json', switch.BIRTH / 'manifest.json')
        import os
        from unittest.mock import Mock
        from provision_realm import UUID
        base, _ = switch.prior_funding()
        runner = object.__new__(switch.TalentRunner)
        runner.funded, runner.before = True, set(range(1, 43))
        runner.original = json.loads((switch.BIRTH / 'replay.json').read_text())
        runner.raw = json.loads((switch.BIRTH / 'manifest.json').read_text())
        runner.account_row = Mock(return_value=dict(id=4, security=0))
        runner.all_offline, runner.trainer_guard = Mock(), Mock()
        def query(sql):
            if '@@server_uuid' in sql: return [dict(uuid=UUID)]
            if 'salt,verifier' in sql: return [{}]
            if 'WHERE account=4' in sql: return [dict(guid=r['guid']) for r in base['characters'] if r['account']==4]
            table = sql.split('acore_characters.')[1].split()[0]
            key = 'character_guid' if table.endswith('binding') else 'guid' if table.startswith('character_') else 'binding_id'
            value = 35 if key in ('guid', 'character_guid') else 25
            rows = [r for r in base[table] if r[key] == value]
            if 'SELECT base_spell' in sql: return [dict(base_spell=r['base_spell']) for r in rows]
            if 'SELECT spell,specMask' in sql:
                return sorted([dict(spell=r['spell'], specMask=r['specMask']) for r in rows], key=lambda r:r['spell'])
            return sorted(rows, key=lambda r:r.get('item_index', 0))
        runner.query = query
        runner.character = lambda _: next(r for r in base['characters'] if r['guid'] == 35)
        with patch.dict(os.environ, WOWPILAGO_TEST_ACCOUNT_PASSWORD='test-only'), patch('provision_realm.check_account'):
            runner.preflight()
            self.assertEqual(runner.manifest.checksum, runner.original['binding'][0]['manifest_hash'])
            for value in (0, switch.MONEY-1, switch.MONEY+1):
                runner.character(35)['money'] = value
                with self.assertRaisesRegex(RuntimeError, 'Pristine'):
                    runner.preflight()

    def test_funded_proof_failures_never_spend_move_or_reauthenticate(self):
        require_inputs(*(switch.ROOT / p for p in switch.PRIOR_FUNDING_HASHES))
        from unittest.mock import Mock
        saved, _ = switch.prior_funding()
        for case in ('far', 'not-loaded', 'phase', 'wrong-money', 'missing-money'):
            with self.subTest(case=case), setup_transport(funded=True) as (r, gm, player, events, clock, directory):
                r.funded, r.trainer = True, None
                r.preflight, r.attach_store, r.execute_funded = Mock(), Mock(), Mock()
                r.save = Mock(return_value=saved)
                logins = []
                @contextlib.contextmanager
                def login(account, *, guid):
                    logins.append((account, guid))
                    yield (gm if guid == 13 else player), guid
                r.login = login
                if case == 'far': player.world = (0, 0, 0, 0, 0)
                replies = TRAINER_REPLY + (['Not in world'] if case == 'not-loaded' else [])
                if case == 'phase': replies = [m.replace('Phasemask: 1', 'Phasemask: 2') for m in replies]
                events.append((.2, lambda: [gm.sock.message(m) for m in replies]))
                pinfo = [m.replace('1001g0s0c', '1000g0s0c') for m in CAPTURED_PINFO] if case == 'wrong-money' else []
                events.append((.8, lambda: [gm.sock.message(m) for m in pinfo]))
                with self.assertRaises(RuntimeError):
                    r.continue_funded()
                r.execute_funded.assert_not_called()
                self.assertEqual(logins, [('TEST', 13), ('APV2C', 35)])
                self.assertEqual(player.sock.sent, [])
                self.assertTrue(all(raw[6:] in (switch.say_packet(switch.TRAINER_INFO),
                                               switch.say_packet(switch.MONEY_INFO)) for raw in gm.sock.sent))
                self.assertFalse(list(directory.glob('money*')))

    def test_funded_control_session_cannot_be_reopened(self):
        from unittest.mock import Mock
        r = object.__new__(switch.TalentRunner)
        r.funded, r.funded_gm_used, r.clients = True, True, []
        r.authorize = Mock()
        with patch.object(switch.Runner, 'login', side_effect=AssertionError('auth')):
            with self.assertRaisesRegex(RuntimeError, 'already consumed'):
                with r.login('TEST', guid=13):
                    self.fail('reopened GM session')

    def test_world_process_identity_requires_real_start_ticks_and_boot_id(self):
        stat = '1 (worldserver) S ' + '0 '*18 + '12345 ' + '0 '*30
        boot = '12345678-1234-1234-1234-123456789abc'
        docker = lambda *args: stat if args[-1] == '/proc/1/stat' else boot
        self.assertEqual(switch.world_process_identity(docker)['start_ticks'], 12345)
        for bad in ('', stat.replace('worldserver', 'sh'), stat.replace('12345', '0')):
            with self.assertRaises(RuntimeError):
                switch.world_process_identity(lambda *args: bad if args[-1] == '/proc/1/stat' else boot)
        with self.assertRaises(RuntimeError):
            switch.world_process_identity(lambda *args: stat if args[-1] == '/proc/1/stat' else '')

    def test_funded_gossip_barrier_precedes_real_guarded_talent_transport(self):
        with setup_transport(funded=True) as (_, gm, player, _, _, _):
            player.trainer = observed()
            with self.assertRaisesRegex(RuntimeError, 'Fresh trainer gossip'):
                player.action('learn', 0)
            player.process(0x17D, gossip_packet(4502, 'dual'))
            with self.assertRaises(RuntimeError):
                player.action('learn', 0)  # Unsolicited menu is not a completed hello.
            player.send(0x17B, struct.pack('<Q', RUNTIME_GUID))
            with self.assertRaises(RuntimeError):
                player.action('learn', 0)  # Sending hello without its response is insufficient.
            player.process(0x17D, gossip_packet(4502, 'dual'))
            player.action('learn', 0)
            self.assertEqual(len(player.sock.sent), 2)

    def test_funded_attempt_is_reserved_once_before_runtime_and_has_failure_evidence(self):
        import tempfile
        import os
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'funded-continuation'
            def runtime(evidence):
                attempt = json.loads((directory / 'attempt.json').read_text())
                self.assertEqual(attempt['money_reserved'], 0)
                raise RuntimeError('offline model runtime refusal')
            with patch.object(switch, 'FUNDED_JOURNAL', directory), \
                    patch.object(switch, 'external_grant', return_value=self.grant()), \
                    patch.object(switch, 'source_evidence', return_value={'offline': 'test'}), \
                    patch.object(switch, 'runtime_guard', side_effect=runtime) as guard, \
                    patch('pymysql.connect', side_effect=AssertionError('SQL')), \
                    patch.dict(os.environ, WOWPILAGO_TEST_ACCOUNT_PASSWORD='test-only', WOWPILAGO_DB_PASSWORD='test-only'):
                with self.assertRaisesRegex(RuntimeError, 'runtime refusal'):
                    switch.run(Path('/unused'), Path('/unused'), funded=True)
                with self.assertRaises(FileExistsError):
                    switch.run(Path('/unused'), Path('/unused'), funded=True)
                self.assertEqual(guard.call_count, 1)
            self.assertEqual(json.loads((directory / 'failure.json').read_text())['preserved'], True)
            self.assertFalse((directory / 'money-burned.json').exists())

    def test_funded_readonly_rest_transition_is_source_bounded(self):
        require_inputs(*(switch.ROOT / p for p in switch.PRIOR_FUNDING_HASHES))
        base, _ = switch.prior_funding()
        after = deepcopy(base)
        actor = next(r for r in after['characters'] if r['guid'] == 13)
        self.assertEqual(actor['restState'], 2)
        actor.update(restState=1, rest_bonus=10.1)
        switch.funded_continuity(base, after, login_bookkeeping=True)
        for changes in (dict(rest_bonus=10), dict(restState=3), dict(xp=56)):
            wrong = deepcopy(after)
            next(r for r in wrong['characters'] if r['guid'] == 13).update(changes)
            with self.assertRaises(RuntimeError):
                switch.funded_continuity(base, wrong, login_bookkeeping=True)
        with self.assertRaises(RuntimeError):
            switch.funded_continuity(base, after)  # No allowance before the authorized login.


class ExecutorTests(unittest.TestCase):
    def test_literal_full_talent_response(self):
        # SMSG_TALENTS_INFO 0x4c0, player, free31, two specs, active1.
        raw = bytes.fromhex('001f000000020101cb000000020600000000000000000000000001cb0000000206000000000000000000000000')
        state = switch.parse_talents(raw)
        self.assertEqual((state['free'], state['count'], state['active']), (31, 2, 1))
        self.assertEqual([s['talents'] for s in state['specs']], [{203: 2}, {203: 2}])
        from realm_client import ProtocolError
        for bad in (raw[:-1], raw+b'\0', b'\x01'+raw[1:], raw[:5]+b'\x03'+raw[6:],
                    raw[:6]+b'\x02'+raw[7:], raw[:8]+struct.pack('<I', 1827)+raw[12:],
                    raw[:12]+b'\x03'+raw[13:]):
            with self.assertRaises((RuntimeError, ProtocolError)):
                switch.parse_talents(bad)

    def test_observation_requires_unique_loaded_source_spawn_and_proximity(self):
        self.assertEqual(observed().guid, RUNTIME_GUID)
        self.assertEqual(STATIC_DERIVED_GUID & 0xFFFFFF, 79788)
        other = [line.replace('0001d0', '003039').replace('Low: 464', 'Low: 12345')
                 for line in TRAINER_REPLY]
        self.assertEqual(switch.observe_trainer(other, WORLD, WORLD).guid, 0xf130000396003039)
        for before, after in [('DB GUID: 79788', 'DB GUID: 464'),
                              ('Entry: 918', 'Entry: 919'),
                              ('000396', '000397'), ('Low: 464', 'Low: 465'),
                              ('Phasemask: 1', 'Phasemask: 2'), ('InstanceID: 0', 'InstanceID: 1'),
                              ('Position: -8752.3', 'Position: -8852.3'),
                              ('Current Entry: 918', 'Current Entry: 919')]:
            with self.subTest(after=after), self.assertRaises(RuntimeError):
                switch.observe_trainer([line.replace(before, after) for line in TRAINER_REPLY], WORLD, WORLD)
        for bad in ([], TRAINER_REPLY * 2, TRAINER_REPLY + ['Not in world'],
                    TRAINER_REPLY + ['Notinworld'], TRAINER_REPLY + [TRAINER_REPLY[1]]):
            with self.assertRaises(RuntimeError):
                switch.observe_trainer(bad, WORLD, WORLD)
        for world in (None, (1, *WORLD[1:]), (0, 0, 0, 0, 0)):
            with self.assertRaises(RuntimeError):
                switch.observe_trainer(TRAINER_REPLY, world, WORLD)
            with self.assertRaises(RuntimeError):
                switch.observe_trainer(TRAINER_REPLY, WORLD, world)

    def test_real_transport_requires_exact_observation_for_gossip_and_wipe(self):
        for trainer in (None, observed()):
            c = guarded_client(trainer=trainer)
            with patch.object(switch.SmokeClient, 'send') as transport:
                for guid in (STATIC_DERIVED_GUID, 0xf130000396003039):
                    c.wipe = (guid, 10000)
                    c.allowed_gossip = struct.pack('<QII', guid, 4502, 39)
                    c.gossip = dict(guid=guid, menu=4502)
                    for opcode, payload in ((0x17B, struct.pack('<Q', guid)),
                                            (0x17C, struct.pack('<QII', guid, 4502, 39)),
                                            switch.native_packet('wipe', guid)):
                        with self.assertRaises(RuntimeError):
                            c.send(opcode, payload)
                    with self.assertRaises(RuntimeError):
                        c.process(0x17D, gossip_packet(4502, 'respec', guid))
                    c.pending_respec = True
                    with self.assertRaises(RuntimeError):
                        c.process(0x2AA, struct.pack('<QI', guid, 10000))
                if trainer is None:
                    c.wipe = (RUNTIME_GUID, 10000)
                    with self.assertRaises(RuntimeError):
                        c.menu()
                    with self.assertRaises(RuntimeError):
                        c.send(*switch.native_packet('wipe', RUNTIME_GUID))
                    with self.assertRaises(RuntimeError):
                        c.process(0x17D, gossip_packet(4502, 'dual'))
                transport.assert_not_called()
        c = guarded_client(trainer=observed())
        with patch.object(switch.SmokeClient, 'send') as transport:
            with self.assertRaises(RuntimeError):
                c.process(0x2AA, struct.pack('<QI', RUNTIME_GUID, 10000))
            c.process(0x17D, gossip_packet(4502, 'respec'))
            c.choose('respec')
            self.assertIsNone(c.gossip)
            self.assertTrue(c.pending_respec)
            c.process(0x2AA, struct.pack('<QI', RUNTIME_GUID, 10000))
            c.action('wipe', RUNTIME_GUID)
            self.assertEqual(transport.call_args.args, (0x2AA, struct.pack('<Q', RUNTIME_GUID)))
            with self.assertRaises(RuntimeError):
                c.action('wipe', RUNTIME_GUID)

    def test_trainer_read_command_requires_finite_setup_and_cannot_repeat(self):
        c = guarded_client(guid=13)
        with patch.object(switch.SmokeClient, 'send') as transport:
            for commands, world in ((set(), WORLD), ({switch.GO}, WORLD),
                                    ({switch.GO, switch.SUMMON}, None)):
                c.used_commands = {switch.say_packet(cmd) for cmd in commands}
                c.world = world
                with self.assertRaises(RuntimeError):
                    c.send(0x95, switch.say_packet(switch.TRAINER_INFO))
            transport.assert_not_called()
            c.world = WORLD
            c.send(0x95, switch.say_packet(switch.TRAINER_INFO))
            transport.assert_called_once()
            for cmd in (switch.TRAINER_INFO, '.npc info 918', '.npc select 79788', '.modify money 1'):
                with self.assertRaises(RuntimeError):
                    c.send(0x95, switch.say_packet(cmd))
        c = guarded_client()
        with self.assertRaises(RuntimeError):
            c.send(0x95, switch.say_packet(switch.TRAINER_INFO))

    def test_wire_gossip_id_not_database_option(self):
        raw = gossip_packet(10371, 'purchase')
        state = switch.parse_gossip(raw)
        self.assertEqual(state['options'][0]['wire'], 39)
        self.assertEqual(state['options'][0]['price'], 10000000)
        from realm_client import ProtocolError
        for bad in (raw[:-1], raw+b'\0', struct.pack('<Q', 35)+raw[8:]):
            with self.assertRaises((RuntimeError, ProtocolError)):
                switch.parse_gossip(bad)

    def test_durable_exclusive_attempt_and_money_burn(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            j = switch.Journal(Path(tmp))
            j.record('attempt', dict(test_only=True))
            j.record('money-burned', dict(copper=switch.MONEY))
            for name in ('attempt', 'money-burned'):
                with self.assertRaises(FileExistsError):
                    switch.Journal(Path(tmp)).record(name, {})
                self.assertTrue((Path(tmp)/(name+'.json')).read_text())

    def test_transport_allowlist_rejects_before_send(self):
        from unittest.mock import Mock
        c = guarded_client()
        for opcode, payload in ((0x36, b''), (0x95, b'.learn 63644'), (0x13D, struct.pack('<Q',35)),
                                (0x17C, struct.pack('<QII',RUNTIME_GUID,4502,2)),
                                switch.native_packet('wipe',RUNTIME_GUID),
                                (0x12E,struct.pack('<BIBI',0,63680,0,0)),
                                (0x3D,struct.pack('<Q',12))):
            with self.assertRaises(RuntimeError):
                c.send(opcode,payload)
        c.log.assert_not_called()

    def test_full_snapshot_frozen_other_actor_and_history(self):
        base = {'character_inventory':[dict(guid=35,item=1)],
                'mod_archipelago_reward':[dict(binding_id=11,applied=0,item_index=0)],
                'character_skills':[dict(guid=35,skill=1,value=10)]}
        switch.compare_snapshots(base,deepcopy(base))
        for table in base:
            damaged = deepcopy(base)
            damaged[table][0]['corruption'] = True
            with self.assertRaises(RuntimeError):
                switch.compare_snapshots(base,damaged)

    def test_ambient_world_timer_and_source_spawn_changes_keep_raw_snapshots(self):
        from verify_artisan_runtime import SOURCE
        require_inputs(SOURCE)
        base = {'worldstates': [dict(entry=3781, value=707455, comment=None),
                                dict(entry=3801, value=0, comment='protected')],
                'creature_respawn': [dict(guid=128894, mapId=609, instanceId=0, respawnTime=1792453143)]}
        after = deepcopy(base)
        after['worldstates'][0]['value'] = 466281
        after['creature_respawn'] = [dict(guid=128893, mapId=609, instanceId=0, respawnTime=1792453351)]
        original = deepcopy((base, after))
        for setup in (False, True):
            audit = switch.compare_snapshots(base, after, setup=setup)
            self.assertTrue(audit['protected_comparison_passed'])
            self.assertEqual(set(audit['ambient_world_audit']), set(base))
        self.assertEqual((base, after), original)
        self.assertEqual(switch.ambient_creature_spawns()[128893], 609)
        switch.compare_snapshots(after, base)  # NPC respawn row additions/deletions are world-owned.

    def test_source_pinned_cold_wind_event_respawns(self):
        from verify_artisan_runtime import SOURCE
        require_inputs(SOURCE)
        spawns = switch.ambient_creature_spawns()
        self.assertTrue(all(spawns[guid] == 571 for guid in (53048, 53049, *range(53051, 53063))))
        self.assertNotIn(53050, spawns)
        row = dict(guid=53055, mapId=571, instanceId=0, respawnTime=1792487002)
        switch.compare_ambient('creature_respawn', [row], [])
        switch.compare_ambient('creature_respawn', [], [row])
        for damaged in (dict(row, mapId=0), dict(row, instanceId=1), dict(row, guid=53050)):
            with self.subTest(row=damaged), self.assertRaises(RuntimeError):
                switch.compare_ambient('creature_respawn', [damaged], [])

    def test_ambient_worldstate_rejects_unknown_keys_new_rows_and_bad_shapes(self):
        base = {'worldstates': [dict(entry=3781, value=707455, comment=None),
                                dict(entry=3801, value=0, comment=None)]}
        mutations = []
        for value in (-1, 2**32, True, '466281', 1.5):
            row = deepcopy(base)
            row['worldstates'][0]['value'] = value
            mutations.append(row)
        for index, key, value in ((0, 'comment', 'changed'), (1, 'value', 1),
                                  (0, 'extra', 1), (0, 'entry', 999999)):
            row = deepcopy(base)
            row['worldstates'][index][key] = value
            mutations.append(row)
        mutations += [{'worldstates': base['worldstates'][1:]},
                      {'worldstates': base['worldstates'] + [dict(entry=999999, value=0, comment=None)]},
                      {'worldstates': base['worldstates'] * 2}]
        for after in mutations:
            with self.subTest(after=after), self.assertRaises(RuntimeError):
                switch.compare_snapshots(base, after)

    def test_ambient_respawns_preserve_ap_trainer_instance_and_unknown_rows(self):
        from verify_artisan_runtime import SOURCE
        require_inputs(SOURCE)
        for guid, map_id, instance in [(g, 0, 0) for g in switch.AP_MERCHANT_SPAWNS] + [
                (switch.TRAINER_SPAWN, 0, 0), (128893, 609, 1), (99999999, 0, 0), (128893, 0, 0)]:
            base = {'creature_respawn': [dict(guid=guid, mapId=map_id, instanceId=instance, respawnTime=10)]}
            after = deepcopy(base)
            after['creature_respawn'][0]['respawnTime'] = 20
            for changed in (after, {'creature_respawn': []}):
                with self.subTest(guid=guid, map_id=map_id, instance=instance), self.assertRaises(RuntimeError):
                    switch.compare_snapshots(base, changed)
                with self.assertRaises(RuntimeError):
                    switch.compare_snapshots(changed, base)

    def test_ambient_respawn_shape_and_unsigned_types_are_not_ignored(self):
        from verify_artisan_runtime import SOURCE
        require_inputs(SOURCE)
        base = {'creature_respawn': [dict(guid=128893, mapId=609, instanceId=0, respawnTime=10)]}
        for key, value in (('guid', 0), ('respawnTime', -1), ('respawnTime', 2**32),
                           ('respawnTime', True), ('mapId', 2**16), ('instanceId', '0'), ('extra', 1)):
            after = deepcopy(base)
            after['creature_respawn'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                switch.compare_snapshots(base, after)
        with self.assertRaises(RuntimeError):
            switch.compare_snapshots(base, {'creature_respawn': base['creature_respawn'] * 2})

    def test_ambient_changes_never_hide_private_gameplay_or_unknown_tables(self):
        from verify_artisan_runtime import SOURCE
        require_inputs(SOURCE)
        ambient = {'worldstates': [dict(entry=3781, value=100, comment=None)], 'creature_respawn': []}
        for table in ('character_inventory', 'item_instance', 'mail', 'character_queststatus',
                      'mod_archipelago_ability', 'unknown_new_table'):
            base = dict(ambient, **{table: [dict(guid=35, value=1)]})
            after = deepcopy(base)
            after['worldstates'][0]['value'] = 90
            after[table][0]['value'] = 2
            with self.subTest(table=table), self.assertRaises(RuntimeError):
                switch.compare_snapshots(base, after)
        for table, row, key in (
                ('characters', dict(guid=35, xp=0, level=50, power4=100), 'xp'),
                ('characters', dict(guid=4, xp=197, level=1), 'xp'),
                ('mod_archipelago_progress', dict(binding_id=11, talent_unlocks=0), 'talent_unlocks'),
                ('mod_archipelago_reward', dict(binding_id=11, applied=0, item_index=0), 'applied')):
            base = dict(ambient, **{table: [row]})
            after = deepcopy(base)
            after['worldstates'][0]['value'] = 90
            after[table][0][key] += 1
            with self.subTest(table=table, row=row), self.assertRaises(RuntimeError):
                switch.compare_snapshots(base, after)
        with self.assertRaises(RuntimeError):
            switch.compare_snapshots(ambient, dict(ambient, new_table=[]))

    def test_raw_snapshot_all_keeps_ambient_and_unknown_tables(self):
        runner = object.__new__(switch.TalentRunner)
        raw = {'creature_respawn': [dict(guid=128897, mapId=609, instanceId=0, respawnTime=10)],
               'worldstates': [dict(entry=3781, value=100, comment=None)],
               'unknown_table': [dict(private_value='retained')]}
        def query(sql):
            if sql.startswith('SELECT TABLE_NAME'):
                return [dict(name=table) for table in raw]
            return deepcopy(raw[sql.split('`')[1]])
        runner.query = query
        self.assertEqual(runner.snapshot_all(), raw)

    def test_owned_cleanup_outside_socket_context_on_body_and_connect_failure(self):
        for fail_connect in (False, True):
            events = []
            runner = object.__new__(switch.TalentRunner)
            runner.clients = []
            runner.funded = False
            runner.authorize = lambda: events.append('grant')
            runner.offline = lambda guid: events.append('offline-' + str(guid))
            @contextlib.contextmanager
            def root_login(*args, **kwargs):
                events.append('socket-open')
                try:
                    if fail_connect:
                        raise ValueError('connect')
                    yield object(), 13
                finally:
                    events.append('socket-closed')
            with patch.object(switch.Runner, 'login', root_login):
                with self.assertRaises(ValueError):
                    with runner.login('TEST', guid=13):
                        raise ValueError('body')
            self.assertEqual(events, ['grant', 'socket-open', 'socket-closed', 'offline-13'])

    def test_exact_ingress_reserves_before_receive_then_same_index_replay(self):
        import tempfile
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as tmp:
            r = object.__new__(switch.TalentRunner)
            r.authorize = Mock()
            r.journal, r.prefix = switch.Journal(Path(tmp)), [{}]*6
            def receive(index, items):
                self.assertTrue((Path(tmp)/'ingress-intent.json').exists())
                self.assertEqual(index, 6)
                self.assertEqual([i['item'] for i in items], [919100020])
                return True
            r.store = Mock()
            r.store.receive.side_effect = receive
            r.ingress()
            r.ingress(replay=True)
            self.assertEqual(r.store.receive.call_args_list[0], r.store.receive.call_args_list[1])
            with self.assertRaises(FileExistsError):
                r.ingress()
            self.assertEqual(r.store.receive.call_count, 2)

    def test_typed_gossip_selection_uses_observed_wire_index(self):
        from unittest.mock import Mock
        c = guarded_client(trainer=observed())
        c.process(0x17D, gossip_packet(10371, 'purchase'))
        with patch.object(switch.SmokeClient, 'send') as transport:
            c.choose('purchase')
            transport.assert_called_once_with(0x17C, struct.pack('<QII',RUNTIME_GUID,10371,39))
            self.assertIsNone(c.gossip)
            with self.assertRaises(RuntimeError):
                c.choose('purchase')
        c.process(0x17D, gossip_packet(10371, 'purchase'))
        c.gossip['options'].append(c.gossip['options'][0])
        with self.assertRaises(RuntimeError):
            c.choose('purchase')

    def test_actual_root_capture_hash_provenance_and_literal_choices(self):
        import hashlib
        original = switch.FUNDED_JOURNAL / 'funded-readonly-proof.json'
        require_inputs(original, FIXTURE_DIR / 'ACTUAL-funded-readonly-proof.json')
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), CAPTURE_HASH)
        self.assertEqual(original.read_bytes(), (FIXTURE_DIR / 'ACTUAL-funded-readonly-proof.json').read_bytes())
        root = captured_root()
        self.assertEqual((root['menu'], root['title']), (4502, 4835))
        self.assertEqual([o['text'] for o in root['options']], [
            'Can you train me how to use rogue skills?', 'I wish to unlearn my Talents.',
            'How do I learn Dual Specialization?', '<Take the letter>'])
        self.assertEqual(switch.parse_gossip(encode_gossip(root)), root)
        trainer = switch.TrainerObservation(root['guid'])
        before = deepcopy(root)
        self.assertEqual(switch.resolve_gossip(root, trainer, 'dual'), 2)
        self.assertEqual(switch.resolve_gossip(root, trainer, 'respec'), 1)
        self.assertEqual(root, before)  # Pure resolver has no send/cache/mutation side effects.

    def test_resolver_rejects_fallback_case_whitespace_icon_box_price_and_duplicates(self):
        cases = (
            ('dual', 'I wish to know about Dual Talent Specialization.'),
            ('respec', 'I wish to unlearn my talents.'),
            ('purchase', 'Purchase a Dual Talent Specialization.'))
        for purpose, fallback in cases:
            menu = 10371 if purpose == 'purchase' else 4502
            good = switch.parse_gossip(gossip_packet(menu, purpose))
            self.assertEqual(switch.resolve_gossip(good, observed(), purpose), 39)
            option = good['options'][0]
            alterations = [('text', fallback), ('text', option['text'].lower()),
                           ('text', ' ' + option['text']), ('text', option['text'] + ' '),
                           ('text', option['text'] + '\n'), ('icon', 1),
                           ('box', 'confirm'), ('box', option['box'] + ' '),
                           ('price', option['price'] + 1)]
            if purpose == 'purchase':
                alterations.append(('box', ''))
            for field, value in alterations:
                with self.subTest(purpose=purpose, field=field, value=value):
                    wrong = deepcopy(good)
                    wrong['options'][0][field] = value
                    with self.assertRaises(RuntimeError):
                        switch.resolve_gossip(wrong, observed(), purpose)
            for options in ([], [option, option | dict(wire=40)]):
                with self.assertRaises(RuntimeError):
                    switch.resolve_gossip(good | dict(options=options), observed(), purpose)

    def test_resolver_rejects_wrong_sender_menu_trainer_and_unknown_purpose(self):
        root = switch.parse_gossip(model_root_packet())
        for bad in (root | dict(guid=STATIC_DERIVED_GUID), root | dict(menu=10371),
                    root | dict(guid=35), None):
            with self.assertRaises(RuntimeError):
                switch.resolve_gossip(bad, observed(), 'dual')
        for trainer in (None, object(), switch.TrainerObservation(35)):
            with self.assertRaises(RuntimeError):
                switch.resolve_gossip(root, trainer, 'dual')
        for purpose in ('', 'DUAL', 'training', 'wipe', None):
            with self.assertRaisesRegex(RuntimeError, 'Unknown gossip operation'):
                switch.resolve_gossip(root, observed(), purpose)

    def test_parser_rejects_coded_duplicate_wires_and_unapproved_respec_menu(self):
        root = captured_root()
        duplicate = deepcopy(root)
        duplicate['options'][1]['wire'] = duplicate['options'][0]['wire']
        for raw in (encode_gossip(root, coded=1), encode_gossip(duplicate),
                    encode_gossip(root | dict(menu=4461))):
            with self.assertRaises(RuntimeError):
                switch.parse_gossip(raw)

    def test_missing_root_choices_stop_before_first_learn_ingress_or_mutation(self):
        require_inputs(FIXTURE_DIR / 'ACTUAL-funded-readonly-proof.json')
        from unittest.mock import Mock
        for funded in (False, True):
            for missing in ((1,), (2,), (1, 2)):
                with self.subTest(funded=funded, missing=missing):
                    c = guarded_client(trainer=observed(), funded=funded)
                    root = switch.parse_gossip(model_root_packet())
                    c.gossip = deepcopy(root)  # A prior valid menu must not rescue the fresh failure.
                    root['options'] = [o for o in root['options'] if o['wire'] not in missing]
                    def wait(predicate, label):
                        c.process(0x17D, encode_gossip(root))
                        self.assertTrue(predicate())
                    c.wait = wait
                    c.state, c.action = Mock(), Mock()
                    runner = object.__new__(switch.TalentRunner)
                    runner.ingress, runner.save = Mock(), Mock()
                    @contextlib.contextmanager
                    def login(*args, **kwargs):
                        yield c, 35
                    runner.login = login
                    with patch.object(switch.SmokeClient, 'send') as transport:
                        with self.assertRaisesRegex(RuntimeError, 'No unique source-confirmed'):
                            runner.execute_funded({})
                        transport.assert_called_once_with(0x17B, struct.pack('<Q', RUNTIME_GUID))
                    c.state.assert_not_called()
                    c.action.assert_not_called()
                    runner.ingress.assert_not_called()
                    runner.save.assert_not_called()

    def test_selection_resolves_new_wire_and_rejects_stale_allowed_wire(self):
        c = guarded_client(trainer=observed())
        c.process(0x17D, model_root_packet())
        self.assertEqual(switch.resolve_gossip(c.gossip, c.trainer, 'dual'), 2)
        fresh = switch.parse_gossip(model_root_packet())
        fresh['options'][2]['wire'] = 91  # Synthetic selection-boundary variation.
        c.process(0x17D, encode_gossip(fresh))
        with patch.object(switch.SmokeClient, 'send') as transport:
            c.choose('dual')
            wire = struct.pack('<QII', RUNTIME_GUID, 4502, 91)
            transport.assert_called_once_with(0x17C, wire)
            self.assertIsNone(c.allowed_gossip)
            with self.assertRaises(RuntimeError):
                c.send(0x17C, wire)
            c.process(0x17D, gossip_packet(10371, 'purchase'))
            c.allowed_gossip = wire
            with self.assertRaises(RuntimeError):
                c.send(0x17C, wire)
            self.assertEqual(transport.call_count, 1)

    def test_selection_preserves_menu_until_real_guarded_send_succeeds(self):
        c = guarded_client(trainer=observed())
        c.process(0x17D, gossip_packet(4502, 'respec'))
        prior = deepcopy(c.gossip)
        with patch.object(switch.SmokeClient, 'send', side_effect=RuntimeError('transport failed')):
            with self.assertRaisesRegex(RuntimeError, 'transport failed'):
                c.choose('respec')
        self.assertEqual(c.gossip, prior)
        self.assertIsNone(c.allowed_gossip)  # Existing once-only gate still burns before transport.
        self.assertFalse(c.pending_respec)

    def test_postpurchase_root_requires_only_current_respec(self):
        c = guarded_client(trainer=observed(), funded=True)
        c.process(0x17D, model_root_packet(purchased=True))
        with self.assertRaises(RuntimeError):
            switch.resolve_gossip(c.gossip, c.trainer, 'dual')
        with patch.object(switch.SmokeClient, 'send') as transport:
            c.choose('respec')
            transport.assert_called_once_with(0x17C, struct.pack('<QII', RUNTIME_GUID, 4502, 1))
        c.process(0x2AA, struct.pack('<QI', RUNTIME_GUID, 10000))
        self.assertEqual(c.wipe, (RUNTIME_GUID, 10000))

    def test_actual_source_broadcast_projection_matches_independent_literals_and_archive(self):
        import hashlib
        from verify_artisan_runtime import SOURCE
        source = SOURCE / 'data/sql/base/db_world'
        require_inputs(source, FIXTURE_DIR / 'world-language-rows.json', FIXTURE_DIR / 'source-sql')
        projection = switch.gossip_source_projection(source)
        expected = {
            'dual': (33762, 'How do I learn Dual Specialization?', 0, ''),
            'respec': (62295, 'I wish to unlearn my Talents.', 0, ''),
            'purchase': (33765, 'I wish to learn Dual Specialization.', 10000000,
                         'Are you sure you wish to purchase a Dual Talent Specialization?'),
        }
        for purpose, values in expected.items():
            self.assertEqual(tuple(projection[purpose][k] for k in ('broadcast', 'text', 'price', 'box')),
                             values)
        audit = json.loads((FIXTURE_DIR / 'world-language-rows.json').read_text())
        for table in ('gossip_menu', 'gossip_menu_option', 'broadcast_text'):
            archived = FIXTURE_DIR / 'source-sql' / (table + '.sql')
            self.assertEqual(hashlib.sha256(archived.read_bytes()).hexdigest(),
                             audit['source_base'][table]['sha256'])
            self.assertEqual(archived.read_bytes(), (source / archived.name).read_bytes())
            switch.verify_dump_rows(archived, audit['installed_rows'][table])
            switch.verify_dump_rows(archived, audit['source_base'][table]['rows'])
        synthetic = switch.parse_gossip(gossip_packet(10371, 'purchase'))['options'][0]
        for key in ('text', 'price', 'icon', 'box'):
            self.assertEqual(synthetic[key], projection['purchase'][key])

    def test_source_projection_refuses_consumer_fallback_or_invented_box(self):
        from verify_artisan_runtime import SOURCE
        source = SOURCE / 'data/sql/base/db_world'
        require_inputs(source)
        for purpose, menu, fallback, price in (
                ('dual', 4502, 'I wish to know about Dual Talent Specialization.', 0),
                ('respec', 4502, 'I wish to unlearn my talents.', 0),
                ('purchase', 10371, 'Purchase a Dual Talent Specialization.', 10000000)):
            with patch.dict(switch.GOSSIP, {purpose: (menu, fallback, price)}):
                with self.assertRaisesRegex(RuntimeError, 'broadcast projection differs'):
                    switch.gossip_source_projection(source)
        with patch.dict(switch.GOSSIP_BOX, {'purchase': 'confirm'}):
            with self.assertRaisesRegex(RuntimeError, 'broadcast projection differs'):
                switch.gossip_source_projection(source)

    def test_broadcast_selected_rows_reject_missing_duplicate_and_changed_gender(self):
        require_inputs(FIXTURE_DIR / 'source-sql/broadcast_text.sql')
        rows = switch.verify_dump_rows(FIXTURE_DIR / 'source-sql/broadcast_text.sql', None)
        self.assertEqual([int(r['ID']) for r in rows],
                         [7491, 8260, 8716, 8717, 33761, 33762, 33765, 60961, 62295])
        wrong_gender = deepcopy(rows)
        next(r for r in wrong_gender if r['ID'] == 33762)['FemaleText'] = 'wrong'
        for wrong in (rows[:-1], rows + [rows[0]], wrong_gender):
            with self.assertRaises(RuntimeError):
                switch.verify_dump_rows(FIXTURE_DIR / 'source-sql/broadcast_text.sql', wrong)

    def test_different_localized_options_fail_closed_without_normalization(self):
        require_inputs(FIXTURE_DIR / 'world-language-rows.json')
        audit = json.loads((FIXTURE_DIR / 'world-language-rows.json').read_text())
        tested = 0
        for row in audit['installed_rows']['broadcast_text_locale']:
            if row['ID'] != 33762:
                continue
            for gender in ('MaleText', 'FemaleText'):
                if row[gender] and row[gender] != 'How do I learn Dual Specialization?':
                    root = switch.parse_gossip(gossip_packet(4502, 'dual'))
                    root['options'][0]['text'] = row[gender]
                    with self.assertRaises(RuntimeError):
                        switch.resolve_gossip(root, observed(), 'dual')
                    tested += 1
        self.assertGreater(tested, 0)

    def test_native_state_rejects_wrong_active_and_spent_lists(self):
        from unittest.mock import Mock
        c = object.__new__(switch.TalentClient)
        c.talent_serial, c.spells = 0, {26669}
        c.action = Mock()
        c.wait = Mock()
        c.talents = dict(free=31,count=2,active=1,
                        specs=[dict(talents={203:2},glyphs=[0]*6)]*2)
        c.state(1,31,[2,2])
        for active, free, ranks in ((0,31,[2,2]), (1,32,[2,2]), (1,31,[None,2])):
            with self.assertRaises(RuntimeError):
                c.state(active,free,ranks)

    def test_source_tp_exact_zero_xp_event_and_explored_bit(self):
        require_inputs(DBC_DIR / 'AreaTable.dbc')
        areas = DBC(DBC_DIR/'AreaTable.dbc')
        row = areas.rows[1519]
        self.assertEqual(row[10],10)
        base = dict(guid=35,xp=0,level=50,taximask='unchanged',exploredZones=' '.join(['0']*128))
        gm = base | dict(guid=13,level=1)
        before = dict(characters=[base,gm])
        bits = [0]*128
        offset, bit = divmod(row[3],32)
        bits[offset] = 1<<bit
        after = dict(characters=[base | dict(exploredZones=' '.join(map(str,bits))),gm])
        switch.source_tp(before,after,[(1519,0)],[])
        for events in ([],[(1519,1)],[(1519,0),(1519,0)]):
            with self.assertRaises(RuntimeError):
                switch.source_tp(before,after,events,[])
        wrong = deepcopy(after)
        wrong['characters'][0]['xp'] = 1
        with self.assertRaises(RuntimeError):
            switch.source_tp(before,wrong,[(1519,0)],[])

    def test_actual_pinned_menu_dumps_parse_completely(self):
        from verify_artisan_runtime import SOURCE
        require_inputs(SOURCE / 'data/sql/base/db_world')
        for table in ('trainer','gossip_menu','gossip_menu_option','conditions','creature_default_trainer',
                      'broadcast_text'):
            path = SOURCE/'data/sql/base/db_world'/(table+'.sql')
            rows = switch.verify_dump_rows(path,None)
            self.assertTrue(rows)
            switch.verify_dump_rows(path,rows)
            with self.assertRaises(RuntimeError):
                switch.verify_dump_rows(path,rows[:-1])

    def test_single_template_schema_maps_only_zero_alternatives(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'creature.sql'
            for second, third in ((0, 0), (919, 0), (0, 919)):
                path.write_text('CREATE TABLE `creature` (\n  `guid` int,\n  `id1` int,\n'
                                '  `id2` int,\n  `id3` int\n);\nINSERT INTO `creature` VALUES\n'
                                f'(79788,918,{second},{third});\n')
                row = dict(guid=79788, id=918)
                if second or third:
                    with self.assertRaisesRegex(RuntimeError, 'cannot represent source alternatives'):
                        switch.verify_dump_rows(path, [row])
                else:
                    switch.verify_dump_rows(path, [row])
                    for wrong in (row | dict(id=919), row | dict(extra=0), dict(guid=79788)):
                        with self.assertRaises(RuntimeError):
                            switch.verify_dump_rows(path, [wrong])

    def test_complete_executor_sequence_with_offline_native_model(self):
        self.workflow_model()

    def test_complete_funded_workflow_with_guarded_clients_and_no_setup(self):
        self.workflow_model(funded=True)

    def workflow_model(self, *, funded=False):
        require_inputs(switch.BIRTH / 'manifest.json', switch.BIRTH / 'replay.json',
                       FIXTURE_DIR / 'ACTUAL-funded-readonly-proof.json')
        from unittest.mock import Mock
        import tempfile
        model = dict(active=0, ranks=[None], unlocks=0, money=switch.MONEY if funded else 0)
        commands, logins, wire_events = [], [], []
        class Player(switch.TalentClient):
            def __init__(self, guid=35):
                self.__dict__.update(guarded_client(guid, r.trainer, funded=funded).__dict__)
                self.exploration, self.responses = [], []
            @property
            def talents(self):
                return dict(count=len(model['ranks']))
            def state(self,active,free,ranks):
                self_test.assertEqual((model['active'],model['ranks']), (active,ranks))
                spent = 0 if ranks[active] is None else ranks[active]+1
                self_test.assertEqual(33+model['unlocks']-spent,free)
            def switch(self,active,free,ranks):
                self.action('switch', active)
                self.state(active,free,ranks)
            def wait(self,predicate,label,*args):
                while self.responses:
                    self.process(*self.responses.pop(0))
                self_test.assertTrue(predicate(),label)
        class GM(Player):
            pass
        def setup_command(gm, player, command, complete):
            gm.send(0x95, switch.say_packet(command))
            commands.append(command)
            if command == switch.GO:
                gm.teleport_serial += 1
                messages = []
            elif command == switch.SUMMON:
                player.teleport_serial += 1
                messages = ['You are summoning ' + switch.PLAYER_LINK + '.']
            elif command == switch.TRAINER_INFO:
                messages = TRAINER_REPLY
            elif command == switch.MONEY_COMMAND:
                model['money'] += switch.MONEY
                messages = [switch.MONEY_SUCCESS]
            else:
                messages = [switch.PINFO_HEADER, '¦ Money: 1001g0s0c', '¦ Online for: 1s']
            self.assertTrue(complete(messages))
            return messages
        def transport(client, opcode, payload=b''):
            wire_events.append((client.guid, opcode, payload))
            if opcode == 0x251:
                self.assertTrue(any(g == 35 and op == 0x17B for g, op, _ in wire_events))
                if funded:
                    self.assertEqual(commands, [switch.TRAINER_INFO, switch.MONEY_INFO])
                talent, rank = struct.unpack('<II', payload)
                self.assertEqual(talent, 203)
                model['ranks'][model['active']] = rank
            elif opcode == 0x12E:
                model['active'] = int(struct.unpack_from('<I', payload, 1)[0] == 63644)
            elif opcode == 0x2AA:
                self.assertEqual(payload, bytes.fromhex('d0010096030030f1'))
                model['ranks'][model['active']] = None
                model['money'] -= 10000
            elif opcode == 0x17B:
                self.assertEqual(payload, struct.pack('<Q', RUNTIME_GUID))
                client.responses.append((0x17D, model_root_packet(purchased=len(model['ranks']) == 2)))
            elif opcode == 0x17C:
                self.assertIsNotNone(client.gossip, 'last menu must survive until send guard')
                _, menu, _ = struct.unpack('<QII', payload)
                if menu == 10371:
                    model['ranks'].append(None)
                    model['money'] -= 10000000
                elif len(model['ranks']) == 1:
                    client.responses.append((0x17D, gossip_packet(10371, 'purchase')))
                else:
                    client.responses.append((0x2AA, struct.pack('<QI', RUNTIME_GUID, 10000)))
            elif opcode == 0x13D:
                self.assertEqual(payload, struct.pack('<Q', 35))
            else:
                self.assertEqual(opcode, 0x95)
        self_test = self
        with tempfile.TemporaryDirectory() as tmp:
            r = object.__new__(switch.TalentRunner)
            r.journal = switch.Journal(Path(tmp), funded=funded)
            r.checkpoint = 0
            r.funded = funded
            r.trainer = None
            r.manifest = object()
            r.raw = json.loads((switch.BIRTH/'manifest.json').read_text())
            r.original = json.loads((switch.BIRTH/'replay.json').read_text())
            r.names = {35:'Apsckmrzjjql'}
            r.preflight = Mock()
            r.setup_command = setup_command
            r.query = Mock(return_value=r.original['binding'])
            r.character = lambda guid: dict(money=model['money'])
            @contextlib.contextmanager
            def login(account,*,guid):
                logins.append((account,guid))
                yield (GM(13) if guid==13 else Player()),guid
            r.login = login
            def save(label):
                r.checkpoint+=1
                return dict(characters=[dict(guid=35,money=model['money'])],
                            mod_archipelago_reward=[dict(applied=0)]*11)
            r.save = save
            def ingress(replay=False):
                if not replay: model['unlocks']+=1
            r.ingress = ingress
            r.receipts = Mock()
            with patch('bridge.v2.Store'), patch.object(switch,'compare_snapshots'), \
                    patch.object(switch,'source_tp'), patch.object(switch,'assert_saved'), \
                    patch.object(switch.SmokeClient, 'send', transport), \
                    patch.object(switch, 'prior_funding', return_value=({}, {})), \
                    patch.object(switch, 'pristine_funded'), patch.object(switch, 'funded_continuity'):
                if funded:
                    r.continue_funded()
                    self.assertFalse((Path(tmp) / 'money-burned.json').exists())
                    self.assertTrue((Path(tmp) / 'funded-readonly-proof.json').exists())
                else:
                    r.execute()
        self.assertEqual(commands, [switch.TRAINER_INFO, switch.MONEY_INFO] if funded else
                         [switch.GO,switch.SUMMON,switch.TRAINER_INFO,switch.MONEY_COMMAND,switch.MONEY_INFO])
        if funded:
            self.assertFalse(any(op == 0x13D for _, op, _ in wire_events))
        self.assertEqual(r.trainer.guid, RUNTIME_GUID)
        self.assertEqual(model,dict(active=0,ranks=[None,2],unlocks=1,money=0))
        self.assertEqual(logins.count(('TEST',13)),1)
        self.assertEqual(logins.count(('APV2C',35)),6)

    def test_saved_masks_and_evasion_survive_primary_reset(self):
        data = dict(characters=[dict(guid=35,level=50,race=1,**{'class':4},talentGroupsCount=2,
                                     activeTalentGroup=0,money=0,resettalents_cost=10000)],
                    character_talent=[dict(guid=35,spell=13792,specMask=2)],
                    character_spell=[dict(guid=35,spell=s,specMask=255) for s in (5277,26669)])
        switch.assert_saved(data,active=0,ranks=[None,2],money=0)
        for table,column,value in (('character_talent','specMask',3),('character_spell','specMask',1),
                                   ('characters','money',1)):
            wrong = deepcopy(data)
            wrong[table][0][column]=value
            with self.assertRaises(RuntimeError):
                switch.assert_saved(wrong,active=0,ranks=[None,2],money=0)

    def test_nonzero_glyph_and_duplicate_talent_rejected(self):
        header=struct.pack('<BIBB',0,30,1,0)
        glyphs=struct.pack('<B6H',6,1,0,0,0,0,0)
        with self.assertRaises(RuntimeError):
            switch.parse_talents(header+b'\0'+glyphs)
        duplicate=header+b'\x02'+struct.pack('<IBIB',203,1,203,2)+struct.pack('<B6H',6,*([0]*6))
        with self.assertRaises(RuntimeError):
            switch.parse_talents(duplicate)

    def test_archived_source_evidence_is_local_and_pins_actual_config_and_helpers(self):
        import verify_artisan_runtime as a
        require_inputs(a.BUILD / 'manifest.json', a.SOURCE, switch.BIRTH,
                       switch.ROOT / '.local/v2-realm/config/worldserver.conf')
        with patch.object(a, 'ROOT', a.SOURCE / 'modules/mod-archipelago'), \
                patch.object(a,'docker',side_effect=AssertionError('runtime inspection')):
            evidence=switch.source_evidence()
        self.assertFalse(evidence['fresh_native_verification'])
        self.assertEqual(evidence['helpers']['tests/verify_talent_switch_runtime.py'],a.digest(Path(switch.__file__)))
        self.assertIn('AreaTable',evidence['dbc_sha256'])
        self.assertEqual(evidence['config_sha256'],a.digest(switch.ROOT/'.local/v2-realm/config/worldserver.conf'))
        for path in ('Globals/ObjectMgr.cpp', 'Globals/ObjectMgr.h', 'Entities/Player/PlayerGossip.cpp',
                     'Entities/Creature/GossipDef.cpp', 'Handlers/QueryHandler.cpp'):
            name = 'src/server/game/' + path
            self.assertEqual(evidence['source_hashes'][name], a.digest(a.SOURCE / name))
        self.assertEqual(evidence['gossip_option_projection']['dual']['text'],
                         'How do I learn Dual Specialization?')
        self.assertEqual(evidence['source_hashes']['data/sql/base/db_world/broadcast_text.sql'],
                         '6f227246c33732ee9e9ee5bd8e1fa6b641aef2b9f4784c69088b898470423734')

    def test_normal_core_fee_achievement_counters_are_exact(self):
        import time
        now=int(time.time())
        row=lambda criterion,counter: dict(guid=35,criteria=criterion,counter=counter,date=now)
        before=dict(characters=[dict(guid=35,resettalents_cost=10000)],
                    character_achievement=[],character_achievement_progress=[row(12698,100)])
        after=deepcopy(before)
        after['character_achievement']=[dict(guid=35,achievement=2716,date=now)]
        after['character_achievement_progress']=[row(12698,110),row(9619,1),row(3359,1),row(3360,10000)]
        for table in ('character_achievement','character_achievement_progress'):
            switch.achievement_changes(before,after,table,setup=False)
        wrong=deepcopy(after)
        wrong['character_achievement_progress'][-1]['counter']=20000
        with self.assertRaises(RuntimeError):
            switch.achievement_changes(before,wrong,'character_achievement_progress',setup=False)
        wrong=deepcopy(after)
        wrong['character_achievement_progress'].append(row(12345,1))
        with self.assertRaises(RuntimeError):
            switch.achievement_changes(before,wrong,'character_achievement_progress',setup=False)

    def test_setup_money_and_exploration_statistics_not_global_exclusions(self):
        import time
        before=dict(characters=[dict(guid=35,resettalents_cost=0)],character_achievement_progress=[])
        after=deepcopy(before)
        after['character_achievement_progress']=[dict(guid=35,criteria=c,counter=n,date=int(time.time()))
                                               for c,n in ((4224,switch.MONEY),(1149,1))]
        switch.achievement_changes(before,after,'character_achievement_progress',setup=True)
        after['character_achievement_progress'][0]['guid']=13
        with self.assertRaises(RuntimeError):
            switch.achievement_changes(before,after,'character_achievement_progress',setup=True)

    def test_runtime_guard_accepts_only_pinned_image_config_dbc_and_docker_defaults(self):
        import hashlib
        import verify_artisan_runtime as a
        config='MinDualSpecLevel = 40\nNoResetTalentsCost = 0\n'
        info=dict(State=dict(Running=True, StartedAt='2026-10-20T00:00:00.000Z'),Image=a.IMAGE,Id='offline-test-only',
                  Config=dict(Labels={'com.docker.compose.project':'wow-test',
                                     'com.docker.compose.service':'worldserver'},
                              Cmd=['-c','/work/install/etc/worldserver.conf'],
                              Env=['AC_FORCE_CREATE_DB=1','AC_UPDATES_ENABLE_DATABASES=0',
                                   'AC_DISABLE_INTERACTIVE=1','AC_CLOSE_IDLE_CONNECTIONS=0']),
                  Mounts=[dict(Destination='/work/install',RW=False,Source=str(a.BUILD/'install'))])
        evidence=dict(build=dict(world_sha256='world-test'),
                      config_sha256=hashlib.sha256(config.encode()).hexdigest(),dbc_sha256={'Spell':'dbc-test'})
        def docker(*args):
            if args[0]=='inspect': return json.dumps([info])
            if args[-1]=='/proc/1/stat': return '1 (worldserver) S ' + '0 '*18 + '1234 ' + '0 '*30
            if args[-1]=='/proc/sys/kernel/random/boot_id': return '12345678-1234-1234-1234-123456789abc'
            if args[2]=='cat': return config
            return ('dbc-test' if args[-1].endswith('.dbc') else 'world-test')+' filename'
        with patch.object(a,'docker',side_effect=docker):
            result = switch.runtime_guard(evidence)
            self.assertEqual(result['container'],'offline-test-only')
            self.assertEqual(result['StartedAt'], '2026-10-20T00:00:00.000Z')
            self.assertEqual(result['world_process_identity']['start_ticks'], 1234)
            started = info['State'].pop('StartedAt')
            with self.assertRaisesRegex(RuntimeError, 'StartedAt'):
                switch.runtime_guard(evidence)
            info['State']['StartedAt'] = started
            info['Config']['Env'].append('AC_MIN_DUAL_SPEC_LEVEL=1')
            with self.assertRaises(RuntimeError):
                switch.runtime_guard(evidence)

    def test_dump_decoder_compares_full_selected_rows(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'trainer.sql'
            p.write_text("CREATE TABLE `trainer` (\n  `Id` int,\n  `name` text\n);\nINSERT INTO `trainer` VALUES\n(9,'Hello, rogue!'),\n(10,'other');\n")
            switch.verify_dump_rows(p,[dict(Id=9,name='Hello, rogue!')])
            for rows in ([],[dict(Id=9,name='bad')]):
                with self.assertRaises(RuntimeError):
                    switch.verify_dump_rows(p,rows)


if __name__ == '__main__':
    unittest.main()
