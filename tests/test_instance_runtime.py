import copy
import struct
import unittest
from unittest.mock import patch

import verify_instance_runtime as live
from integration_inputs import require_inputs


class InstanceGuards(unittest.TestCase):
    def test_offline_plan_never_probes_or_authenticates(self):
        with patch('socket.create_connection', side_effect=AssertionError('network')), \
                patch.object(live.transfer, 'probe_source', side_effect=AssertionError('probe')), patch('builtins.print'):
            self.assertEqual(live.main([]), 0)

    def test_setup_only_once_on_selected23(self):
        client = live.InstanceClient(None, lambda *_: None, 13)
        command = live.say_packet('.additem 756 1')
        with patch.object(live.SmokeClient, 'send'), patch.object(live.transfer, 'emit'):
            client.add_reserved = True
            with self.assertRaises(RuntimeError):
                client.send(0x95, command)
            client.send(0x13D, struct.pack('<Q', 23))
            client.send(0x95, command)
            with self.assertRaises(RuntimeError):
                client.send(0x95, command)
            for text in ('.additem 756 2', '.learn 172', '.modify money 1', '.archipelago equip 286 15'):
                client.add_reserved = True
                with self.assertRaises(RuntimeError):
                    client.send(0x95, live.say_packet(text))
            with self.assertRaises(RuntimeError):
                client.send(0x13D, struct.pack('<Q', 22))

    def test_native_mainhand_packets_only(self):
        client = live.InstanceClient(None, lambda *_: None, 23)
        client.ordinary = 999
        with patch.object(live.SmokeClient, 'send') as send, patch.object(live.transfer, 'emit'):
            for guid in (286, 999):
                packet = live.equip_packet(guid, 15)
                self.assertEqual(struct.unpack('<QB', packet), ((0x4000 << 48) | guid, 15))
                client.send(0x10F, packet)
            self.assertEqual(send.call_count, 2)
            for opcode, payload in ((0x10F, live.equip_packet(285, 15)),
                                    (0x10F, live.equip_packet(286, 0)), (0x36, b''),
                                    (0x238, b''), (0x256, b''), (0x95, live.say_packet('.additem 756 1'))):
                with self.assertRaises(RuntimeError):
                    client.send(opcode, payload)
        for guid in (1, 4, 22, 94):
            with self.assertRaises(RuntimeError):
                live.InstanceClient(None, lambda *_: None, guid).send(0x37)

    def test_level_denial_has_actual_guid_and_required_level(self):
        payload = struct.pack('<BQQBI', 1, (0x4000 << 48) | 999, (0x4000 << 48) | 286, 0, 24)
        live.level_denial(payload, 999)
        for invalid in (b'\x01', payload[:-1], b'\x02' + payload[1:], payload[:-4] + struct.pack('<I', 60)):
            with self.assertRaises(RuntimeError):
                live.level_denial(invalid, 999)
        with self.assertRaises(RuntimeError):
            live.level_denial(payload, 998)

    def test_ordinary_copy_must_be_exact_owned_and_unauthorized(self):
        item = dict(guid=999, itemEntry=756, owner_guid=23, count=1, flags=0, duration=0, enchantments='0 0 ')
        snapshot = dict(fixtures={'23': dict(items=[item], authorized=[dict(item_guid=286)],
                                           inventory=[dict(item=999, bag=0, slot=26)])})
        self.assertEqual(live.ordinary_instance(snapshot), item)
        for change in (dict(owner_guid=22), dict(flags=1), dict(count=2), dict(enchantments='1 0')):
            invalid = copy.deepcopy(snapshot)
            invalid['fixtures']['23']['items'][0].update(change)
            with self.assertRaises(RuntimeError):
                live.ordinary_instance(invalid)
        invalid = copy.deepcopy(snapshot)
        invalid['fixtures']['23']['authorized'].append(dict(item_guid=999))
        with self.assertRaises(RuntimeError):
            live.ordinary_instance(invalid)

    def test_reservation_blocks_second_setup_after_interruption(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        runner = object.__new__(live.InstanceRunner)
        state = dict(fixtures={'23': dict(items=[dict(guid=286, itemEntry=756)])})
        with TemporaryDirectory() as tmp, patch.object(live, 'OUTPUT', Path(tmp)), \
                patch.object(runner, 'saved', return_value=state), patch.object(runner, 'facts'), \
                patch.object(runner, 'login', side_effect=AssertionError('simulated interruption')) as login:
            with self.assertRaises(AssertionError):
                runner.setup_ordinary()
            with self.assertRaises(FileExistsError):
                runner.setup_ordinary()
            self.assertEqual(login.call_count, 1)

    def test_setup_attestation_reuses_without_auth_or_second_add(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        runner = object.__new__(live.InstanceRunner)
        item = dict(guid=999, itemEntry=756, owner_guid=23, count=1, flags=0, duration=0, enchantments='0 0 ')
        state = dict(fixtures={'23': dict(items=[item], authorized=[dict(item_guid=286)],
                                         inventory=[dict(item=999, bag=0, slot=26)])},
                     entry_authorizations=[dict(item_guid=286)])
        with TemporaryDirectory() as tmp, patch.object(live, 'OUTPUT', Path(tmp)), \
                patch.object(runner, 'saved', return_value=state), patch.object(runner, 'facts'), \
                patch.object(runner, 'login', side_effect=AssertionError('authentication')), \
                patch.object(live.transfer, 'emit'):
            root = Path(tmp)
            names = ('setup-before.json', 'setup-after.json', 'setup-command.json')
            for name in names:
                (root / name).write_text('{}')
            proof = dict(owner=23, command='.additem 756 1', ordinary_item=item, no_authorization=True,
                         hashes={n: live.transfer.digest((root / n).read_bytes()) for n in names})
            (root / 'setup-attestation.json').write_text(json.dumps(proof))
            self.assertEqual(runner.setup_ordinary(), 999)
            state['entry_authorizations'].append(dict(item_guid=999))
            with self.assertRaises(RuntimeError):
                runner.setup_ordinary()

    def test_same_player_equip_then_ordinary_denial(self):
        from contextlib import contextmanager
        from pathlib import Path
        from tempfile import TemporaryDirectory
        runner = object.__new__(live.InstanceRunner)
        item = dict(guid=999, itemEntry=756, owner_guid=23, count=1, flags=0, duration=0, enchantments='0 0 ')
        before = dict(fixtures={'23': dict(items=[item], authorized=[dict(item_guid=286)], inventory=[
            dict(bag=0, slot=15, item=266), dict(bag=0, slot=25, item=286), dict(bag=0, slot=26, item=999)])})
        equipped = copy.deepcopy(before)
        equipped['fixtures']['23']['inventory'] = [dict(bag=0, slot=15, item=286),
                                                  dict(bag=0, slot=25, item=266), dict(bag=0, slot=26, item=999)]
        clients = []

        @contextmanager
        def login(guid):
            self.assertEqual(guid, 23)
            from unittest.mock import Mock
            player = Mock(errors=[])
            if clients:
                def deny(*_):
                    player.errors.append(struct.pack('<BQQBI', 1, (0x4000 << 48) | 999,
                                                     (0x4000 << 48) | 286, 0, 24))
                player.send.side_effect = deny
            clients.append(player)
            yield player

        with TemporaryDirectory() as tmp, patch.object(runner, 'facts'), \
                patch.object(runner, 'saved', side_effect=[before, equipped, equipped, equipped]), \
                patch.object(runner, 'login', login), patch.object(runner, 'offline'):
            runner.compare(999, Path(tmp))
        clients[0].send.assert_called_once_with(0x10F, live.equip_packet(286, 15))
        clients[1].send.assert_called_once_with(0x10F, live.equip_packet(999, 15))

    def test_native_source_preconditions(self):
        require_inputs(live.transfer.SOURCE)
        source = live.transfer.SOURCE
        storage = (source / 'src/server/game/Entities/Player/PlayerStorage.cpp').read_text()
        self.assertIn('sScriptMgr->OnPlayerCheckItemLevel(this, instance, ignoreRequiredLevel)', storage)
        self.assertIn('return EQUIP_ERR_CANT_EQUIP_LEVEL_I;', storage)
        item = (source / 'src/server/game/Handlers/ItemHandler.cpp').read_text()
        self.assertIn('_player->GetItemByGuid(packet.ItemGuid)', item)
        self.assertIn('_player->SwapItem(item->GetPos(), dstpos)', item)
        progression = (source / 'modules/mod-archipelago/src/APProgression.cpp').read_text()
        self.assertIn('state->authorizedItems.find(item->GetGUID().GetCounter())', progression)
        self.assertIn('item->GetOwnerGUID() != player->GetGUID()', progression)
        auction = (source / 'src/server/game/Handlers/AuctionHouseHandler.cpp').read_text()
        self.assertLess(auction.index('!item->CanBeTraded()'), auction.index('item->GetCount() < count[i]'))
        self.assertLess(auction.index('item->GetCount() < count[i]'), auction.index('GetAuctionDeposit'))


if __name__ == '__main__':
    unittest.main()
