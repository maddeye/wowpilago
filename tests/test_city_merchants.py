import copy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import verify_city_merchants as city
from integration_inputs import require_inputs

NPC = (0xF130 << 48) | (900500 << 24) | 123


def packet(labels):
    return struct.pack('<QIII', NPC, 0, 68, len(labels)) + b''.join(
        struct.pack('<IBBI', i, 0, 0, 0) + text.encode() + b'\0' + box.encode() + b'\0'
        for i, (text, box) in enumerate(labels)) + b'\0\0\0\0'


class CityGuards(unittest.TestCase):
    def test_full_menu_request_keeps_last_reply_until_select_is_validated(self):
        player = city.CityClient(None, lambda *_: None, 24)
        player.allowed_selection = NPC
        root = packet([(text, '') for text in ('status', 'Weapons / shields / held items',
                       'Armor / cloaks', 'Jewelry / trinkets', 'Set pieces')])
        replies = [root] + [p for _ in range(4) for p in (root, packet([]))]
        player.stay = lambda _: player.process(0x17D, replies.pop(0))
        runner = object.__new__(city.CityRunner)
        runner.bounded = lambda: None
        with patch('verify_runtime.SmokeClient.send') as wire, patch('verify_travel_runtime.emit'):
            pages = runner.menus(player)
        self.assertEqual(len(pages), 5)
        self.assertEqual(replies, [])
        self.assertEqual(wire.call_count, 9)

    def transport_case(self, *, far=False, fault=None, index=0, actor=24):
        clock = [100.0]
        gm = city.CityClient('gm-wire', lambda *_: None, 13)
        player = city.CityClient('player-wire', lambda *_: None, actor)
        spawn = city.spawns()[index]
        gm.route_guid, gm.route_spawn = actor, spawn
        gm.commands = city.command_set(actor, spawn)
        for client in (gm, player):
            client.world = (1 if far else spawn['map'], 0, 0, 0, 0)
            client.next_ping = 10000
        runner = object.__new__(city.CityRunner)
        runner.deadline = 130
        if fault == 'runner-deadline':
            runner.deadline = 100.6
        queues = {gm.sock: [], player.sock: []}
        driven, sent = set(), []
        def tp(client):
            point = city.control_anchor(spawn) if client is gm else spawn
            x, y, z = [point['position_' + a] for a in 'xyz']
            if fault == 'distance':
                x += 5.01
            if far:
                return 0x3E, struct.pack('<Iffff', spawn['map'] + (fault == 'map'), x, y, z, 0)
            guid = 37 if fault == 'guid' else client.guid
            return 0xC7, bytes([1, guid]) + struct.pack('<IIIHffff', 7, 0, 0, 0, x, y, z, 0)
        def wire(client, opcode, payload=b''):
            if opcode in (0xDC, 0xC7) and fault == 'ack':
                raise RuntimeError('ACK failed')
            if opcode == 0x95:
                command = payload[8:-1].decode()
                sent.append((clock[0], command))
                target = gm if command.startswith('.go ') else player
                if target is player:
                    self.assertEqual(len(gm.teleport_evidence), 1)
                    self.assertGreater(clock[0], 101)
                    name = city.OWNERS[actor][2]
                    destination = city.destinations()[index]['name']
                    text = f'You are teleporting |cffffffff|Hplayer:{name}|h[{name}]|h|r to {destination}.'
                    if fault == 'offline':
                        text = text.replace('|h|r to ', '|h|r (offline) to ')
                    if fault == 'wrong-actor':
                        text = text.replace(name, 'Other')
                    if fault == 'wrong-name':
                        text = text.replace(' to ' + destination + '.', ' to WrongName.')
                    raw = struct.pack('<BIQIQI', 0, 0, 0, 0, 0, len(text) + 1) + text.encode() + b'\0\0'
                    if fault != 'no-reply':
                        queues[gm.sock].append((clock[0] + .1, (0x96, raw)))
                    if fault == 'saved-position':
                        player.world = (spawn['map'], *(spawn['position_' + a] for a in 'xyz'), 0)
                if fault == 'error':
                    text = '|cffffffff|Hplayer:Apsfjnnrfebe|h[Apsfjnnrfebe]|h|r is already being teleported.'
                    raw = struct.pack('<BIQIQI', 0, 0, 0, 0, 0, len(text) + 1) + text.encode() + b'\0\0'
                    queues[gm.sock].append((clock[0] + .1, (0x96, raw)))
                if fault != 'timeout' and not (target is player and fault == 'saved-position'):
                    queues[target.sock].append((clock[0] + 1.4, tp(target)))
        def select(read, _w, _e, timeout):
            sock, = read
            driven.add(sock)
            due = queues[sock][0][0] if queues[sock] else float('inf')
            if due <= clock[0] + timeout:
                clock[0] = max(clock[0], due)
                return [sock], [], []
            clock[0] += timeout
            return [], [], []
        def receive(client):
            return queues[client.sock].pop(0)[1]
        def release():
            city.require(fault != 'release' or clock[0] < 100.6, 'release expired')
        with patch.object(city, 'parent_release', side_effect=release) as releases, \
                patch('time.monotonic', side_effect=lambda: clock[0]), \
                patch('time.monotonic_ns', side_effect=lambda: int(clock[0] * 1e9)), \
                patch('realm_client.select.select', side_effect=select), \
                patch('realm_client.RealmClient.send', autospec=True, side_effect=wire), \
                patch('realm_client.RealmClient.receive', autospec=True, side_effect=receive), \
                patch('verify_travel_runtime.emit'), patch.object(city.transfer, 'emit') as events:
            go, = [c for c in gm.commands if c.startswith('.go ')]
            teleport, = [c for c in gm.commands if c.startswith('.tele name ')]
            if fault == 'old':
                gm.process(*tp(gm))
                queues[gm.sock].clear()
                fault = 'timeout'
            try:
                runner.complete_transport(gm, player, spawn, go)
                runner.complete_transport(gm, player, spawn, teleport)
            except RuntimeError:
                self.assertIn('city_command_unresolved', [c.args[0] for c in events.call_args_list])
                raise
        self.assertGreater(releases.call_count, 4)
        self.assertEqual(driven, {gm.sock, player.sock})
        self.assertEqual(len(sent), 2)
        self.assertEqual(len(player.teleport_evidence), 1)

    def test_delayed_real_client_near_and_far_complete_before_summon(self):
        require_inputs(city.TELE_SQL)
        for far in (False, True):
            with self.subTest(far=far):
                self.transport_case(far=far)

    def test_transport_strict_failures(self):
        require_inputs(city.TELE_SQL)
        for fault in ('guid', 'distance', 'ack', 'offline', 'error', 'timeout', 'old',
                      'saved-position', 'no-reply', 'runner-deadline', 'release', 'wrong-actor', 'wrong-name'):
            with self.subTest(fault=fault), self.assertRaises(RuntimeError):
                self.transport_case(fault=fault)
        with self.assertRaises(RuntimeError):
            self.transport_case(far=True, fault='map')

    def test_transport_requires_authorized_command_and_real_client_guard(self):
        require_inputs(city.TELE_SQL)
        runner = object.__new__(city.CityRunner)
        gm = city.CityClient(None, lambda *_: None, 13)
        player = city.CityClient(None, lambda *_: None, 24)
        with self.assertRaisesRegex(RuntimeError, 'Unsafe transport'):
            runner.complete_transport(gm, player, city.spawns()[0], '.gm on')
        runner.deadline = city.time.monotonic() + 30
        runner.bounded = lambda: None
        with patch.object(city.transfer, 'emit'), self.assertRaisesRegex(RuntimeError, 'Unsafe GM command'):
            runner.complete_transport(gm, player, city.spawns()[0],
                                      next(c for c in city.command_set(24, city.spawns()[0]) if c.startswith('.go ')))

    def test_only_controlled_capital_resting_flag_may_change(self):
        for guid in (13, 24, 37):
            before = dict(guid=guid, playerFlags=0, xp=0, money=0, level=32)
            self.assertEqual(city.character_projection(before),
                             city.character_projection(dict(before, playerFlags=0x20)))
            for changes in (dict(playerFlags=0x28), dict(xp=1), dict(money=1), dict(level=33)):
                self.assertNotEqual(city.character_projection(before),
                                    city.character_projection(dict(before, **changes)))
        protected = dict(guid=4, playerFlags=0, xp=143)
        self.assertNotEqual(city.character_projection(protected),
                            city.character_projection(dict(protected, playerFlags=0x20)))

    def test_binding_datetime_matches_archived_text_but_changes_still_fail(self):
        row = dict(id=14, created_at=datetime(2026, 10, 19, 18, 5, 51),
                   manifest_hash='original', status='offline', heartbeat=123)
        archived = dict(row, created_at='2026-10-19 18:05:51', status='online', heartbeat=456)
        self.assertEqual(city.immutable_binding(row), city.immutable_binding(archived))
        for change in (dict(created_at='2026-10-19 18:05:52'), dict(manifest_hash='changed')):
            self.assertNotEqual(city.immutable_binding(row), city.immutable_binding(dict(archived, **change)))

    def test_default_zero_observations_no_network_or_sql_or_runtime(self):
        require_inputs(city.TELE_SQL)
        with patch('socket.create_connection', side_effect=AssertionError('network')), \
                patch.object(city.artisan, 'docker', side_effect=AssertionError('runtime')), \
                patch.object(city.Runner, 'query', side_effect=AssertionError('SQL')), \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(city.main([]), 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(plan['live_observations'], 0)
        self.assertEqual(len(plan['spawns']), 10)
        self.assertFalse(plan['network_without_run'])

    def test_literal_menu_and_purchase_not_navigation(self):
        data = packet([('Vouchers: 9 | Remaining total cost: 6', ''),
                       ('Weapons / shields / held items', ''),
                       ('#0 |cffa335ee|Hitem:868:0:0:0:0:0:0:0|h[Ardent Custodian]|h|r | 6 vouchers | Buy one', 'Buy one for 6 vouchers?')])
        menu = city.gossip_packet(data)
        expected = [dict(stock_index=0, item_entry=868, price=6, sold=False)]
        self.assertEqual(city.menu_stock([menu], expected, 9)['remaining_cost'], 6)
        self.assertEqual(city.navigation(menu, 1), struct.pack('<QII', NPC, 0, 1))
        with self.assertRaises(RuntimeError):
            city.navigation(menu, 2)
        for broken in (data[:-1], data + b'x', data[:23]):
            with self.assertRaises((RuntimeError, UnicodeDecodeError)):
                city.gossip_packet(broken)
        for change in ({'price': 5}, {'sold': True}, {'item_entry': 756}):
            with self.assertRaises(RuntimeError):
                city.menu_stock([menu], [dict(expected[0], **change)], 9)
        with self.assertRaises(RuntimeError):
            city.menu_stock([menu, menu], expected, 9)

    def test_complete_stock_at_supported_sizes(self):
        for count in (30, 60, 120):
            expected = [dict(stock_index=i, item_entry=1000 + i, price=1, sold=False) for i in range(count)]
            menus = []
            for start in range(0, count, 10):
                labels = [(f'Vouchers: 0 | Remaining total cost: {count}', '')]
                labels += [(f'#{i} |cff0070dd|Hitem:{1000+i}:0:0:0:0:0:0:0|h[Item {i}]|h|r | 1 vouchers | Buy one', 'Buy one for 1 vouchers?')
                           for i in range(start, min(start + 10, count))]
                menus.append(city.gossip_packet(packet(labels)))
            self.assertEqual(len(city.menu_stock(menus, expected, 0)['stock']), count)
            with self.assertRaises(RuntimeError):
                city.menu_stock(menus[:-1], expected, 0)

    def test_sold_and_balance(self):
        menu = city.gossip_packet(packet([('Vouchers: 3 | Remaining total cost: 0', ''),
                ('#2 |cff0070dd|Hitem:756:0:0:0:0:0:0:0|h[Tunnel Pick]|h|r | 1 vouchers | SOLD', '')]))
        expected = [dict(stock_index=2, item_entry=756, price=1, sold=True)]
        city.menu_stock([menu], expected, 3)
        with self.assertRaises(RuntimeError):
            city.menu_stock([menu], expected, 4)

    def test_source_cities_and_unsafe_tp(self):
        require_inputs(city.TELE_SQL)
        self.assertEqual([s['guid'] for s in city.spawns()], list(range(9005000, 9005010)))
        self.assertEqual(city.spawns()[3]['map'], 530)
        self.assertEqual(city.spawns()[7]['map'], 530)
        commands = city.command_set(37, city.spawns()[7])
        self.assertIn('.tele name Apsflewguljo SilvermoonCity', commands)
        self.assertFalse(any(c.startswith('.summon ') for c in commands))
        for guid, index in ((4, 0), (24, 4), (37, 0)):
            with self.assertRaises(RuntimeError):
                city.command_set(guid, city.spawns()[index])
        client = city.CityClient(None, lambda *_: None, 13)
        client.route_guid, client.route_spawn = 24, city.spawns()[0]
        client.commands = city.command_set(24, city.spawns()[0])
        for command in ('.tele name Apsfjnnrfebe Darnassus', '.modify money 10000',
                        '.summon Other', '.go xyz 0 0 0 0', '.learn 100'):
            with self.assertRaises(RuntimeError):
                client.send(0x95, city.say_packet(command))
        for opcode in (0x36, 0x10F, 0x13D, 0x12E, 0x238):
            with self.assertRaises(RuntimeError):
                client.send(opcode)

    def test_release_guard_and_no_auth_on_missing_release(self):
        now = datetime.now(timezone.utc)
        release = dict(owned_release=True, gui40_released=True, mail46_released=True,
                       native_matrix_released=True, all_native_owners_released=True,
                       all_offline=True, no_other_runners=True, world_sha256=city.transfer.WORLD_HASH,
                       release_id='unit-test-not-a-grant', issued_utc=now.isoformat(),
                       expires_utc=(now + timedelta(minutes=20)).isoformat())
        city.release_guard(release, now)
        for change in ({k: False} for k, v in release.items() if v is True):
            with self.assertRaises(RuntimeError):
                city.release_guard(dict(release, **change), now)
        for change in ({'world_sha256': 'old'}, {'release_id': ''},
                       {'expires_utc': (now - timedelta(seconds=1)).isoformat()},
                       {'expires_utc': (now + timedelta(hours=1)).isoformat()}):
            with self.assertRaises(RuntimeError):
                city.release_guard(dict(release, **change), now)
        with patch.object(city, 'parent_release', side_effect=RuntimeError('unreleased')), \
                patch.object(city.transfer, 'probe_source') as source:
            with self.assertRaises(RuntimeError):
                city.main(['--run'])
            source.assert_not_called()

    def test_ownership_missing_birth_cannot_add_known(self):
        require_inputs(city.ROOT / '.local/city-merchants-plan/ownership-hashes.json')
        runner = object.__new__(city.CityRunner)
        runner.known, runner.names = set(), {}
        original = city.load
        def changed(path):
            value = original(path)
            if path == '.local/travel-live/creation.json':
                value['guid'] = 4
            return value
        with patch.object(city, 'load', side_effect=changed), patch.object(runner, 'query', side_effect=AssertionError('too early')):
            with self.assertRaisesRegex(RuntimeError, 'trusted birth'):
                runner.ownership()
        self.assertEqual(runner.known, set())

    def test_original_ownership_and_current_receipt_mutation(self):
        require_inputs(city.ROOT / '.local/city-merchants-plan/ownership-hashes.json',
                       city.ROOT / '.local/travel-extension/final-observations.json',
                       city.ROOT / city.CASE7 / 'replay.json')
        runner = object.__new__(city.CityRunner)
        runner.known, runner.names = set(), {}
        proofs = {24: city.load('.local/travel-extension/final-observations.json'),
                  37: city.load(city.CASE7 + 'replay.json')}
        def query(sql, args=()):
            guid = 24 if args[0] in (7, 14, 24) else 37
            proof = proofs[guid]
            if 'salt,verifier' in sql:
                return [{}]
            if 'mod_archipelago_binding' in sql:
                return proof['binding']
            if 'mod_archipelago_reward' in sql:
                return proof.get('receipts', proof.get('rewards'))
            if 'mod_archipelago_progress' in sql:
                return proof['progress']
            self.fail(sql)
        def account(name):
            guid = 24 if name == 'APV2F' else 37
            return dict(id=city.OWNERS[guid][1], username=name, email='wowpilago-fixture@invalid', security=0, online=0)
        def character(guid):
            if guid == 13:
                return dict(guid=13, xp=55, playerFlags=0, extra_flags=0)
            a = city.OWNERS[guid]
            return dict(guid=guid, account=a[1], name=a[2], race=a[3], **{'class': a[4]}, level=a[5], online=0)
        with patch.object(runner, 'account_row', side_effect=account), patch.object(runner, 'character', side_effect=character), \
                patch.object(runner, 'query', side_effect=query), patch.object(city, 'check_account'), \
                patch.object(runner, 'reuse_control'):
            runner.ownership()
            self.assertEqual(runner.known, {24, 37})
            runner.known.clear()
            mutated = copy.deepcopy(proofs[24]['rewards'])
            mutated[0]['ap_item'] += 1
            def bad_query(sql, args=()):
                return mutated if 'mod_archipelago_reward' in sql else query(sql, args)
            with patch.object(runner, 'query', side_effect=bad_query):
                with self.assertRaisesRegex(RuntimeError, 'receipt prefix'):
                    runner.ownership()
            self.assertEqual(runner.known, set())

    def test_reservation_preserves_previous_fail(self):
        with TemporaryDirectory() as tmp, patch.object(city, 'OUTPUT', Path(tmp)), \
                patch.object(city, 'parent_release', return_value={}), patch.object(city, 'source_evidence', return_value={}), \
                patch.dict('os.environ', WOWPILAGO_DB_PASSWORD='test-only', WOWPILAGO_TEST_ACCOUNT_PASSWORD='test-only'), \
                patch.object(city.artisan, 'docker', side_effect=AssertionError('must stop first')):
            (Path(tmp) / 'attempt.json').write_text('{}')
            summary = Path(tmp) / 'summary.json'
            summary.write_text('{"status":"FAIL","error":"preserve me"}')
            with self.assertRaises(FileExistsError):
                city.main(['--run'])
            self.assertEqual(json.loads(summary.read_text())['error'], 'preserve me')

    def test_archived_pinned_core_and_modeled_helper_integrity(self):
        require_inputs(city.artisan.BUILD / 'manifest.json', city.artisan.SOURCE,
                       city.ROOT / '.local/city-merchants-plan/exploration-source-review.json')
        load = city.load
        # Model helper integrity separately from the historical runtime approval inventory.
        with TemporaryDirectory(dir=city.ROOT / '.local') as tmp:
            helper = Path(tmp) / 'helper.py'
            helper.write_text('# reviewed unit-test helper\n')
            inventory = {str(helper.relative_to(city.ROOT)): city.artisan.digest(helper)}
            def inputs(path):
                return inventory if path == '.local/city-merchants-plan/helper-hashes.json' else load(path)
            with patch.object(city, 'load', side_effect=inputs), \
                    patch.object(city.artisan, 'ROOT', city.artisan.SOURCE / 'modules/mod-archipelago'), \
                    patch.object(city.artisan, 'docker', side_effect=AssertionError('runtime forbidden')), \
                    patch('socket.create_connection', side_effect=AssertionError('network forbidden')), \
                    patch('realm_client.authenticate', side_effect=AssertionError('auth forbidden')), \
                    patch.object(city.Runner, 'query', side_effect=AssertionError('SQL forbidden')):
                evidence = city.source_evidence()
                self.assertEqual(evidence['world_sha256'], city.transfer.WORLD_HASH)
                self.assertEqual(evidence['manifest_sha256'], city.transfer.MANIFEST_HASH)
                helper.write_text('# changed after review\n')
                with self.assertRaisesRegex(RuntimeError, 'Native/helper source changed'):
                    city.source_evidence()

    def test_protected_stock_mutation_and_only_owned_exploration(self):
        require_inputs(city.ROOT / '.local/travel-live/manifest.json')
        runner = object.__new__(city.CityRunner)
        before = dict(ap_check=[], character_aura=[], ap_stock=[{'binding_id': 14, 'sold': 0}])
        after = copy.deepcopy(before)
        after['ap_stock'][0]['sold'] = 1
        with patch.object(runner, 'frozen', return_value=after):
            with self.assertRaisesRegex(RuntimeError, 'Protected state'):
                runner.compare(before)
        with patch.object(runner, 'frozen', return_value=copy.deepcopy(before)):
            self.assertEqual(runner.compare(before), [])
        for binding in (11, 14):
            after = copy.deepcopy(before)
            after['ap_check'] = [dict(binding_id=binding, location_id=-1, acknowledged=1)]
            with patch.object(runner, 'frozen', return_value=after):
                with self.assertRaises((RuntimeError, ValueError)):
                    runner.compare(before)

    def test_literal_exploration_packet_through_real_client_parser(self):
        require_inputs(city.XP_TABLE, city.artisan.DBC_DIR / 'AreaTable.dbc')
        client = city.CityClient(None, lambda *_: None, 24)
        client.city, client.phase, client.session = 9, 'teleport', 1
        raw = b'\x2b\x11\x00\x00\xbe\x05\x00\x00'  # Dalaran 4395, 1470 XP
        client.process(0x1F8, raw)
        self.assertEqual(client.exploration_credits, [dict(actor=24, city=9, phase='teleport',
                         session=1, areaId=4395, amount=1470, raw=raw.hex())])
        with self.assertRaisesRegex(RuntimeError, 'Repeated'):
            client.process(0x1F8, raw)
        for guid, index, phase, payload in (
                (13, 9, 'teleport', raw), (42, 9, 'teleport', raw),
                (37, 9, 'teleport', raw), (24, 0, 'teleport', raw),
                (24, 9, 'outside', raw), (24, None, 'login', raw),
                (24, 9, 'teleport', struct.pack('<II', 12, 1470)),
                (37, 5, 'teleport', struct.pack('<II', 4617, 0)),
                (24, 8, 'teleport', struct.pack('<II', 3703, 0)),
                (24, 9, 'teleport', struct.pack('<II', 4395, 1471)),
                (24, 9, 'teleport', raw[:-1]), (24, 9, 'teleport', raw + b'x')):
            with self.subTest(guid=guid, city=index, phase=phase, payload=payload):
                with self.assertRaises(RuntimeError):
                    city.exploration_credit(guid, index, phase, 1, payload)

    def test_exact_exploration_sum_only_owned_xp_and_no_other_exclusions(self):
        require_inputs(city.XP_TABLE, city.artisan.DBC_DIR / 'AreaTable.dbc')
        runner = object.__new__(city.CityRunner)
        before = dict(ap_check=[], character_aura=[], ap_progress=[dict(binding_id=14, xp_bank=0)],
                      characters=[dict(guid=g, xp=55 if g == 13 else 0, level=level, money=10, health=100)
                                  for g, level in ((13, 1), (24, 77), (37, 32), (42, 55), (4, 1))])
        runner.exploration_credits = [
            city.exploration_credit(24, 9, 'teleport', 1, struct.pack('<II', 4395, 1470)),
            city.exploration_credit(37, 4, 'teleport', 2, struct.pack('<II', 1637, 12))]
        after = copy.deepcopy(before)
        after['characters'][1]['xp'] = 1470
        after['characters'][2]['xp'] = 12
        with patch.object(runner, 'frozen', side_effect=lambda: copy.deepcopy(after)):
            self.assertEqual(runner.compare(before), [])
            for index, key, value in ((1, 'xp', 1471), (2, 'xp', 13), (1, 'level', 78),
                                      (1, 'money', 11), (1, 'health', 101), (0, 'xp', 1),
                                      (3, 'xp', 1), (4, 'xp', 1)):
                original = after['characters'][index][key]
                after['characters'][index][key] = value
                with self.subTest(index=index, key=key), self.assertRaises(RuntimeError):
                    runner.compare(before)
                after['characters'][index][key] = original
            after['ap_progress'][0]['xp_bank'] = 1
            with self.assertRaisesRegex(RuntimeError, 'Protected state'):
                runner.compare(before)
            after['ap_progress'][0]['xp_bank'] = 0
            runner.exploration_credits = []
            with self.assertRaisesRegex(RuntimeError, 'XP delta'):
                runner.compare(before)

    def test_control_xp_proposal_cannot_assume_seven_positive_city_areas(self):
        require_inputs(city.XP_TABLE, city.artisan.DBC_DIR / 'AreaTable.dbc',
                       city.artisan.SOURCE / 'data/sql/base/db_world/player_xp_for_level.sql')
        dbc = city.DBC(city.artisan.DBC_DIR / 'AreaTable.dbc')
        positive = []
        for area, row in dbc.rows.items():
            root, seen = area, set()
            while root in dbc.rows and root not in seen and dbc.rows[root][2]:
                seen.add(root)
                root = dbc.rows[root][2]
            if root in city.CITY_AREAS and 0 < row[10] < 0x80000000:
                positive.append(area)
        self.assertEqual(set(positive), set(city.CITY_AREAS) - {3703})
        self.assertIn('(6,55)', city.XP_TABLE.read_text())
        threshold = (city.artisan.SOURCE / 'data/sql/base/db_world/player_xp_for_level.sql').read_text()
        self.assertIn('(1,400)', threshold)
        self.assertGreaterEqual(55 + (len(positive) - 1) * 55, 400)
        with self.assertRaisesRegex(RuntimeError, 'Unexpected exploration actor'):
            city.exploration_credit(13, 1, 'teleport', 1, struct.pack('<II', 1537, 55))

    def test_captured_root_menu_and_near_teleport_guid(self):
        require_inputs(city.ROOT / '.local/city-merchants-plan/rest-reviewed/run.jsonl',
                       city.ROOT / '.local/city-merchants-plan/gossip-reviewed/run.jsonl')
        path = city.ROOT / '.local/city-merchants-plan/rest-reviewed/run.jsonl'
        events = [json.loads(line) for line in path.read_text().splitlines()]
        raw = next(bytes.fromhex(e['raw']) for e in events if e.get('opcode') == '0x17d')
        player = city.CityClient(None, lambda *_: None, 24)
        player.allowed_selection = city.gossip_packet(raw)['npc']
        player.process(0x17D, raw)
        payload = city.navigation(player.menu, player.menu['rows'][1]['option'])
        with patch('realm_client.RealmClient.send') as wire, patch('verify_travel_runtime.emit'):
            player.send(0x17C, payload)
            wire.assert_called_once()
        path = city.ROOT / '.local/city-merchants-plan/gossip-reviewed/run.jsonl'
        event = json.loads(path.read_text().splitlines()[161])
        raw = bytes.fromhex(event['raw'])
        self.assertEqual(city.transfer.packed_guid(raw)[0], 13)
        with self.assertRaisesRegex(RuntimeError, 'Wrong teleport mover'):
            player.process(0xC7, raw)
        gm = city.CityClient(None, lambda *_: None, 13)
        gm.world = (0, 0, 0, 0, 0)
        with patch('realm_client.RealmClient.send'), patch('verify_travel_runtime.emit'), patch.object(city.transfer, 'emit'):
            gm.process(0xC7, raw)
        self.assertEqual(gm.teleports, 1)

    def test_exact_pinned_tele_names_and_separate_friendly_map_anchors(self):
        require_inputs(city.TELE_SQL)
        names = ['Stormwind', 'Ironforge', 'TempleOfTheMoon', 'TheExodar', 'Orgrimmar',
                 'Undercity', 'ThunderBluff', 'SilvermoonCity', 'Shattrath', 'Dalaran']
        self.assertEqual([r['name'] for r in city.destinations()], names)
        for guid, indices in city.CITIES.items():
            for index in indices:
                spawn = city.spawns()[index]
                commands = city.command_set(guid, spawn)
                anchor = city.control_anchor(spawn)
                self.assertIn(city.spawns().index(anchor), (0, 2, 8, 9))
                self.assertEqual(anchor['map'], spawn['map'])
                self.assertIn(f'.tele name {city.OWNERS[guid][2]} {names[index]}', commands)
                self.assertEqual(len(commands), 3)
                self.assertFalse(any(c.startswith(('.summon ', '.gm ')) for c in commands))
                if index in (4, 5, 6, 7):
                    self.assertNotEqual(anchor, spawn)

    def test_future_readonly_tele_preflight_requires_full_pinned_tuple(self):
        require_inputs(city.TELE_SQL)
        runner = object.__new__(city.CityRunner)
        tele = city.destinations()[0]
        for field in city.TELE_COLUMNS:
            wrong = dict(tele)
            wrong[field] = 'WrongName' if field == 'name' else tele[field] + 1
            with self.subTest(field=field), patch.object(runner, 'query', return_value=[wrong]) as query, \
                    patch.object(runner, 'login_owned', side_effect=AssertionError('no login')):
                with self.assertRaisesRegex(RuntimeError, 'full tuple'):
                    runner.execute({})
                self.assertTrue(query.call_args.args[0].startswith('SELECT '))

    def test_pinned_tele_dump(self):
        require_inputs(city.TELE_SQL)
        self.assertGreater(len(city.tele_rows(city.TELE_SQL.read_text())), 1000)

    def test_fixed_dump_csv_validation_not_a_general_sql_parser(self):
        prefix = ('CREATE TABLE `game_tele` (\n'
                  '  `id` int,\n  `position_x` float,\n  `position_y` float,\n'
                  '  `position_z` float,\n  `orientation` float,\n  `map` int,\n'
                  '  `name` text\n);\n')
        text = prefix + "INSERT INTO `game_tele` VALUES\n(1,1,2,3,4,0,'A');\n"
        def dump(tuple_text):
            return prefix + 'INSERT INTO `game_tele` VALUES\n' + tuple_text + '\n'
        self.assertEqual(city.tele_rows(dump("(1,1,2,3,4,0,'A\\'B,C');"))[0]['name'], "A'B,C")
        for broken in ("(1,1,2,3,4,0);", "(x,1,2,3,4,0,'A');", "(1,nan,2,3,4,0,'A');",
                       "(1,1,2,3,4,-1,'A');", "(1,1,2,3,4,0,'A);", "(1,1,2,3,4,0,'');",
                       "(1,1,2,3,4,0,'A');\n(1,1,2,3,4,0,'B');"):
            with self.subTest(broken=broken), self.assertRaises((RuntimeError, ValueError, city.csv.Error)):
                city.tele_rows(dump(broken))
        with self.assertRaisesRegex(RuntimeError, 'column order'):
            city.tele_rows(text.replace('`position_x` float', '`wrong_column` float', 1))

    def test_real_command_guard_rejects_injected_actor_name_and_horde_control_point(self):
        require_inputs(city.TELE_SQL)
        gm = city.CityClient(None, lambda *_: None, 13)
        gm.route_guid, gm.route_spawn = 37, city.spawns()[4]
        approved = city.command_set(37, city.spawns()[4])
        hostile_go = '.go xyz ' + ' '.join(str(city.spawns()[4]['position_' + a]) for a in 'xyz') + ' 1'
        for command in ('.tele name Apsfjnnrfebe Orgrimmar', '.tele name Apsflewguljo 703',
                        '.tele name Apsflewguljo Stormwind', '.tele name Other Orgrimmar',
                        hostile_go, '.summon Apsflewguljo', '.gm on'):
            gm.commands = approved | {command}
            with self.subTest(command=command), self.assertRaisesRegex(RuntimeError, 'Unsafe GM'):
                gm.send(0x95, city.say_packet(command))
        gm.commands = approved
        with self.assertRaisesRegex(RuntimeError, 'approved map anchor'):
            gm.send(0x95, city.say_packet('.tele name Apsflewguljo Orgrimmar'))
        anchor = city.control_anchor(gm.route_spawn)
        gm.world = (anchor['map'], *(anchor['position_' + a] for a in 'xyz'), 0)
        with patch('realm_client.RealmClient.send') as wire, patch('verify_travel_runtime.emit'):
            gm.send(0x95, city.say_packet('.tele name Apsflewguljo Orgrimmar'))
            wire.assert_called_once()

    def test_remote_horde_npc_transport_uses_friendly_control_anchor(self):
        require_inputs(city.TELE_SQL)
        for far in (False, True):
            for index in city.CITIES[37]:
                with self.subTest(index=index, far=far):
                    self.transport_case(index=index, actor=37, far=far)

    def npc_case(self, index=4):
        spawn = city.spawns()[index]
        actor = 37 if index in city.CITIES[37] else 24
        gm = city.CityClient(None, lambda *_: None, 13)
        player = city.CityClient(None, lambda *_: None, actor)
        anchor = city.control_anchor(spawn)
        gm.world = (anchor['map'], *(anchor['position_' + a] for a in 'xyz'), 0)
        player.world = (spawn['map'], *(spawn['position_' + a] for a in 'xyz'), 0)
        messages = [f'DB GUID: {spawn["guid"]}, GUID Full: 0x{NPC:016X} Type: Creature Entry: 900500',
                    'Position: ' + ' '.join(str(spawn['position_' + a]) for a in 'xyz') + '.',
                    'AIName:  ScriptName: archipelago_merchant', 'SpellSchoolImmuneMask: 0']
        return gm, player, spawn, messages

    def test_remote_loaded_native_npc_same_map_only_and_actual_actor_five_yards(self):
        gm, player, spawn, messages = self.npc_case()
        self.assertFalse(city.at_point(gm, spawn))
        self.assertEqual(city.loaded_merchant(gm, player, spawn, messages), NPC)
        for bad in (messages + ['(Not in world - showing DB data)'],
                    [m.replace('9005004,', '9005005,') for m in messages],
                    [m.replace('Entry: 900500', 'Entry: 900501') for m in messages],
                    messages + [messages[0]], messages[:-1],
                    [m if not m.startswith('Position:') else 'Position: 0 0 0.' for m in messages]):
            with self.subTest(messages=bad), self.assertRaises(RuntimeError):
                city.loaded_merchant(gm, player, spawn, bad)
        for target, world in ((gm, (0, *gm.world[1:])), (gm, player.world),
                              (player, (1, player.world[1] + 5.01, *player.world[2:]))):
            original = target.world
            target.world = world
            with self.assertRaises(RuntimeError):
                city.loaded_merchant(gm, player, spawn, messages)
            target.world = original

    def test_native_npc_query_pumps_both_real_clients_and_refuses_db_fallback(self):
        require_inputs(city.TELE_SQL)
        gm, player, spawn, messages = self.npc_case()
        gm.route_guid, gm.route_spawn = player.guid, spawn
        gm.commands = city.command_set(player.guid, spawn)
        runner = object.__new__(city.CityRunner)
        runner.deadline = city.time.monotonic() + 30
        runner.bounded = lambda: None
        driven = []
        def pump(client):
            driven.append(client.guid)
            if client is gm and messages:
                text = messages.pop(0)
                raw = struct.pack('<BIQIQI', 0, 0, 0, 0, 0, len(text) + 1) + text.encode() + b'\0\0'
                client.process(0x96, raw)
        gm.stay = lambda _: pump(gm)
        player.stay = lambda _: pump(player)
        with patch('realm_client.RealmClient.send'), patch('verify_travel_runtime.emit'):
            self.assertEqual(runner.merchant_info(gm, player, spawn), NPC)
        self.assertEqual(set(driven), {13, player.guid})
        gm.messages = []
        messages[:] = ['(Not in world - showing DB data)']
        with patch('realm_client.RealmClient.send'), patch('verify_travel_runtime.emit'), \
                patch.object(city.transfer, 'emit') as events, self.assertRaisesRegex(RuntimeError, 'DB fallback'):
            runner.merchant_info(gm, player, spawn)
        self.assertEqual(events.call_args.args[0], 'city_command_unresolved')

    def test_control_native_xp_ancestry_and_global_session_area_dedup(self):
        require_inputs(city.XP_TABLE, city.artisan.DBC_DIR / 'AreaTable.dbc')
        self.assertEqual(city.control_positive_areas(), {1519: 10, 1657: 10, 4395: 75})
        credits = []
        for session, index, area in ((1, 0, 1519), (2, 2, 1657), (3, 9, 4395)):
            client = city.CityClient(None, lambda *_: None, 13)
            client.city, client.phase, client.session = index, 'teleport', session
            client.exploration_credits = credits
            client.process(0x1F8, struct.pack('<II', area, 55))
        self.assertEqual(sum(c['amount'] for c in credits), 165)
        client.session = 4
        with self.assertRaisesRegex(RuntimeError, 'Repeated'):
            client.process(0x1F8, struct.pack('<II', 4395, 55))
        # A saved friendly login location is role-specific, never the actor's Horde city.
        self.assertEqual(city.exploration_credit(13, 2, 'login', 5, struct.pack('<II', 1519, 55))['amount'], 55)
        for index, phase, area, amount in ((2, 'teleport', 1519, 55), (8, 'teleport', 3703, 0),
                (2, 'login', 1637, 55), (2, 'teleport', 1657, 54), (2, 'teleport', 1657, 56),
                (4, 'login', 1637, 55), (2, 'outside', 1657, 55), (9, 'teleport', 4395, 1470)):
            with self.subTest(index=index, phase=phase, area=area, amount=amount), self.assertRaises(RuntimeError):
                city.exploration_credit(13, index, phase, 1, struct.pack('<II', area, amount))

    def test_only_source_bounded_owned_rested_transition_is_accepted(self):
        runner = object.__new__(city.CityRunner)
        runner.exploration_credits = []
        before = dict(ap_check=[], character_aura=[], characters=[
            dict(guid=37, level=32, xp=0, restState=2, health=100)])
        after = copy.deepcopy(before)
        after['characters'][0]['restState'] = 1
        bonus = 11
        def query(sql, args):
            self.assertEqual((sql, args), ('SELECT rest_bonus FROM acore_characters.characters WHERE guid=%s', (37,)))
            return [dict(rest_bonus=bonus)]
        runner.query = query
        with patch.object(runner, 'frozen', side_effect=lambda: copy.deepcopy(after)):
            self.assertEqual(runner.compare(before), [])
            for bonus in (0, 10):
                with self.assertRaisesRegex(RuntimeError, 'Unproved rested-state'):
                    runner.compare(before)
            bonus = 11
            after['characters'][0]['health'] = 99
            with self.assertRaisesRegex(RuntimeError, 'Protected state'):
                runner.compare(before)
            after['characters'][0]['health'] = 100
            before['characters'][0]['restState'] = 1
            after['characters'][0]['restState'] = 2
            with self.assertRaisesRegex(RuntimeError, 'Unproved rested-state'):
                runner.compare(before)

    def test_control_exact_saved_xp_bound_and_every_other_field_protected(self):
        require_inputs(city.XP_TABLE, city.artisan.DBC_DIR / 'AreaTable.dbc')
        runner = object.__new__(city.CityRunner)
        before = dict(ap_check=[], character_aura=[], characters=[dict(guid=13, level=1, xp=55,
                      playerFlags=0, extra_flags=0, money=0, health=100)])
        runner.exploration_credits = [city.exploration_credit(13, i, 'teleport', s, struct.pack('<II', a, 55))
                                      for s, i, a in ((1, 0, 1519), (2, 2, 1657), (3, 9, 4395))]
        after = copy.deepcopy(before)
        after['characters'][0]['xp'] = 220
        with patch.object(runner, 'frozen', side_effect=lambda: copy.deepcopy(after)):
            self.assertEqual(runner.compare(before), [])
            for key, value in (('xp', 219), ('xp', 221), ('level', 2), ('playerFlags', 8),
                               ('extra_flags', 1), ('money', 1), ('health', 99)):
                original = after['characters'][0][key]
                after['characters'][0][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                    runner.compare(before)
                after['characters'][0][key] = original
            runner.exploration_credits.append(dict(runner.exploration_credits[0], session=4))
            with self.assertRaisesRegex(RuntimeError, 'Duplicate'):
                runner.compare(before)
            runner.exploration_credits = []
            with self.assertRaisesRegex(RuntimeError, 'XP delta'):
                runner.compare(before)

    def test_socket_closes_before_offline_wait_on_body_failure(self):
        runner = object.__new__(city.CityRunner)
        runner.known, runner.names = {37}, {37: 'Apsflewguljo'}
        runner.current_city, runner.sessions, runner.exploration_credits = 4, 0, []
        profile = dict(guid=37, account=4, name='Apsflewguljo', race=2, **{'class': 7})
        from types import SimpleNamespace
        auth = SimpleNamespace(realms=[SimpleNamespace(locked=False, flags=0)])
        order = []
        def connect(client, *_args, **_kwargs):
            client.login = True
            return SimpleNamespace(guid=37)
        with patch.object(runner, 'bounded'), patch.object(runner, 'account_row', return_value={}), \
                patch.object(city, 'guard_account'), patch.object(runner, 'character', return_value=profile), \
                patch('realm_client.authenticate', return_value=auth), \
                patch('socket.create_connection') as connection, \
                patch.object(city.CityClient, 'connect', autospec=True, side_effect=connect), \
                patch.object(city.CityClient, 'logout', side_effect=lambda: order.append('logout')), \
                patch.object(city.CityClient, 'stay'), \
                patch.object(runner, 'offline', side_effect=lambda _: order.append('offline')):
            connection.return_value.__exit__.side_effect = lambda *_: order.append('socket-close')
            with self.assertRaisesRegex(RuntimeError, 'body failed'):
                with runner.login_owned(37):
                    raise RuntimeError('body failed')
        self.assertEqual(order, ['logout', 'socket-close', 'offline'])

    def test_cleanup_offline_even_when_authentication_raises(self):
        runner = object.__new__(city.CityRunner)
        runner.known, runner.names = {37}, {37: 'Apsflewguljo'}
        profile = dict(guid=37, account=4, name='Apsflewguljo', race=2, **{'class': 7})
        with patch.object(runner, 'bounded'), patch.object(runner, 'account_row', return_value={}), \
                patch.object(city, 'guard_account'), patch.object(runner, 'character', return_value=profile), \
                patch('realm_client.authenticate', side_effect=RuntimeError('auth failed')), patch.object(runner, 'offline') as offline:
            with self.assertRaisesRegex(RuntimeError, 'auth failed'):
                with runner.login_owned(37):
                    self.fail('must not yield')
            offline.assert_called_once_with(37)


if __name__ == '__main__':
    unittest.main()
