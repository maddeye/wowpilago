import struct
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, Mock, patch

import verify_transfer_runtime as live
from integration_inputs import require_inputs


class TransferGuards(unittest.TestCase):
    def test_offline_plan(self):
        with patch('socket.create_connection', side_effect=AssertionError('network')), patch('builtins.print'):
            self.assertEqual(live.main([]), 0)

    def test_archived_fixed_source_pin_offline(self):
        require_inputs(live.artisan.BUILD / 'manifest.json', live.SOURCE)
        with patch.object(live.artisan, 'ROOT', live.artisan.SOURCE / 'modules/mod-archipelago'), \
                patch.object(live.artisan, 'docker', side_effect=AssertionError('runtime')):
            evidence = live.probe_source()
        self.assertEqual(evidence['world_sha256'], live.WORLD_HASH)
        self.assertEqual(evidence['manifest_sha256'], live.MANIFEST_HASH)
        self.assertEqual(evidence['patch_sha256'], live.PATCH_HASH)
        self.assertIn('scripts/World/server_mail.cpp', evidence['hashes'])

    def test_release_is_explicit_fresh_and_before_auth(self):
        now = datetime.now(timezone.utc)
        release = dict(owned_release=True, gui40_released=True, mail46_released=True,
                       native_matrix_released=True, world_sha256=live.WORLD_HASH, release_id='parent-exclusive-test',
                       issued_utc=(now - timedelta(seconds=1)).isoformat(),
                       expires_utc=(now + timedelta(minutes=10)).isoformat())
        with TemporaryDirectory() as tmp, patch.object(live, 'OUTPUT', Path(tmp)):
            path = Path(tmp) / 'release.json'
            with self.assertRaises(FileNotFoundError):
                live.parent_release()
            path.write_text(json.dumps(release))
            self.assertEqual(live.parent_release(), release)
            for change in ({'native_matrix_released': False}, {'world_sha256': 'old'},
                           {'expires_utc': (now - timedelta(seconds=1)).isoformat()},
                           {'expires_utc': (now + timedelta(hours=1)).isoformat()}):
                path.write_text(json.dumps(dict(release, **change)))
                with self.assertRaises(RuntimeError):
                    live.parent_release()
            with patch.object(live.artisan, 'runtime_evidence') as runtime:
                with self.assertRaises(RuntimeError):
                    live.runtime_evidence({})
                runtime.assert_not_called()

    def test_preflight_requires_all_accounts_and_characters_offline(self):
        runner = object.__new__(live.TransferRunner)
        with patch.object(live, 'parent_release'), patch.object(runner, 'query', side_effect=[[], []]):
            runner.preflight()
        for rows in (([{'guid': 13}],), ([], [{'id': 1}])):
            with patch.object(live, 'parent_release'), patch.object(runner, 'query', side_effect=rows):
                with self.assertRaises(RuntimeError):
                    runner.preflight()

    def test_login_exception_always_waits_for_owned_fixture_offline(self):
        for failure in ('body', 'logout', 'connect'):
            with self.subTest(failure=failure):
                runner = object.__new__(live.TransferRunner)
                runner.known = {22}
                runner.account_row = Mock()
                runner.character = Mock(return_value={'online': 0})
                order = []
                runner.offline = Mock(side_effect=lambda _: order.append('offline'))
                client = Mock(login=True)
                client.connect.return_value = Mock(guid=22)
                if failure != 'body':
                    getattr(client, failure).side_effect = RuntimeError(failure)
                runner.client_type = Mock(return_value=client)
                realm = Mock(locked=False, flags=0)
                transport = MagicMock()
                transport.__exit__.side_effect = lambda *_: order.append('socket_closed')
                with patch.object(live, 'parent_release'), patch.object(live, 'guard_account'), \
                     patch.object(live, 'guard_character'), patch.object(live, 'emit'), \
                     patch.dict(live.os.environ, {'WOWPILAGO_TEST_ACCOUNT_PASSWORD': 'test-only'}), \
                     patch('realm_client.authenticate', return_value=Mock(realms=[realm])), \
                     patch.object(live.socket, 'create_connection', return_value=transport):
                    with self.assertRaisesRegex(RuntimeError, failure):
                        with runner.login(22):
                            if failure == 'body':
                                raise RuntimeError('body')
                runner.offline.assert_called_once_with(22)
                self.assertEqual(order, ['socket_closed', 'offline'])

    def test_money_cannot_be_added_again(self):
        self.assertNotIn('.modify money 10000', live.COMMANDS)
        client = live.TransferClient(None, lambda *_: None, 13)
        with self.assertRaises(RuntimeError):
            client.send(0x95, live.say_packet('.modify money 10000'))

    def test_mail_layout_and_no_success_route(self):
        mailbox = (0xF110 << 48) | (195603 << 24) | 123
        packet = live.mail_packet(mailbox, (256, 269))
        self.assertEqual(struct.unpack_from('<Q', packet)[0], mailbox)
        rest = packet[8:].split(b'\0', 3)[3]
        self.assertEqual(rest[:9], struct.pack('<IIB', 41, 0, 2))
        self.assertEqual(rest[9:27], struct.pack('<BQBQ', 0, (0x4000 << 48) | 256, 1, (0x4000 << 48) | 269))
        self.assertEqual(rest[27:], bytes(17))
        for items in ((256,), (), (270,), (269, 256)):
            with self.assertRaises(RuntimeError):
                live.mail_packet(mailbox, items)

    def test_auction_layout_and_no_post_control(self):
        npc = (0xF130 << 48) | (8719 << 24) | 123
        self.assertEqual(struct.unpack('<QIQIIII', live.auction_packet(npc, 269)),
                         (npc, 1, (0x4000 << 48) | 269, 1, 100, 0, 720))
        live.auction_packet(npc, 256, 2)
        for item, count in ((256, 1), (270, 1), (269, 2)):
            with self.assertRaises(RuntimeError):
                live.auction_packet(npc, item, count)

    def test_native_guid_required(self):
        npc = (0xF130 << 48) | (8719 << 24) | 123
        message = f'GUID Full: 0x{npc:016x} Type: Creature Entry: 8719 Low: 123'
        self.assertEqual(live.observed_guid([message], 'Creature', 8719), npc)
        mailbox = (0xF110 << 48) | (195603 << 24) | 1011
        self.assertEqual(live.observed_guid([f'GUID: GUID Full: 0x{mailbox:016x} Type: Gameobject Entry: 195603  Low: 1011'],
                                           'GameObject', 195603), mailbox)
        for messages in ([], [message, message], ['Not in world', message]):
            with self.assertRaises(RuntimeError):
                live.observed_guid(messages, 'Creature', 8719)

    def test_creation_and_protected_actions_blocked(self):
        for guid in (13, 22, 23, 94, 1):
            client = live.TransferClient(None, lambda *_: None, guid)
            for opcode, payload in ((0x36, b''), (0x95, live.say_packet('.modify money 99999')),
                                    (0x13D, struct.pack('<Q', 94)), (0x256, b''), (0x238, b''), (0xC7, b'')):
                with self.assertRaises(RuntimeError):
                    client.send(opcode, payload)

    def test_near_teleport_ack(self):
        client = live.TransferClient(None, lambda *_: None, 22)
        client.world = (0, 0, 0, 0, 0)
        with patch.object(client, 'send') as send:
            client.process(0xC7, b'\x01\x16' + struct.pack('<IIHIffffI', 7, 0, 0, 123, 1, 2, 3, 4, 0))
            send.assert_called_once_with(0xC7, b'\x01\x16' + struct.pack('<II', 7, 0))
        self.assertEqual(client.world, (0, 1, 2, 3, 4))
        with self.assertRaises(RuntimeError):
            client.process(0xC7, b'\x01\x17')


if __name__ == '__main__':
    unittest.main()
