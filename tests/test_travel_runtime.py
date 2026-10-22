"""Offline packet/state tests. No realm or database access."""
import contextlib
import io
import struct
import unittest
from unittest.mock import patch

import verify_travel_runtime as travel


def guid(value):
    raw = value.to_bytes(8, 'little')
    return bytes([sum(1 << i for i, b in enumerate(raw) if b)]) + bytes(b for b in raw if b)


class Client(travel.TravelClient):
    def __init__(self):
        self.sent = []
        super().__init__(None, lambda *_: None)

    def send(self, opcode, payload=b''):
        self.sent.append((opcode, payload))


class TravelTests(unittest.TestCase):
    def setUp(self):
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def test_offline_plan(self):
        with patch.object(travel, 'source_evidence', side_effect=AssertionError('network')):
            self.assertEqual(travel.main([]), 0)

    def test_cast_layout_and_bounds(self):
        self.assertEqual(travel.cast_packet(458, 1), struct.pack('<BIBI', 1, 458, 0, 0))
        for spell, count in ((100, 1), (458, 256), (True, 0), (458, -1)):
            with self.assertRaises(RuntimeError):
                travel.cast_packet(spell, count)

    def test_packed_guid(self):
        for value in (0, 24, 0xF130001234005678, 2**64 - 1):
            self.assertEqual(travel.packed_guid(guid(value)), (value, len(guid(value))))
        for data in (b'', b'\xff\x01'):
            with self.assertRaises(RuntimeError):
                travel.packed_guid(data)

    def test_spell_go_requires_full_fixed_header(self):
        packet = guid(24) + guid(24) + struct.pack('<BIII', 3, 458, 0, 123)
        self.assertEqual(travel.spell_go(packet), (24, 24, 3, 458))
        with self.assertRaises(RuntimeError):
            travel.spell_go(packet[:-1])

    def test_worldport_ack_preserves_ping_schedule(self):
        client = Client()
        ping = client.next_ping
        client.process(0x03E, struct.pack('<Iffff', 530, 1, 2, 3, 4))
        self.assertEqual(client.world, (530, 1, 2, 3, 4))
        self.assertEqual(client.sent, [(0x0DC, b'')])
        self.assertEqual(client.next_ping, ping)
        with self.assertRaises(RuntimeError):
            client.process(0x03E, b'')

    def test_near_teleport_ack_and_position(self):
        client = Client()
        client.world = (0, 0, 0, 0, 0)
        client.process(0x0C7, guid(24) + struct.pack('<IIHIffffI', 7, 0, 0, 123, 1, 2, 3, 4, 0))
        self.assertEqual(client.sent, [(0x0C7, guid(24) + struct.pack('<II', 7, 0))])
        self.assertEqual(client.world, (0, 1, 2, 3, 4))
        with self.assertRaises(RuntimeError):
            client.process(0x0C7, guid(24))

    def test_cast_failure_capture(self):
        client = Client()
        client.process(0x130, struct.pack('<BIB', 5, 32239, 60))
        self.assertEqual(client.failures, [(5, 32239, 60)])
        with self.assertRaises(RuntimeError):
            client.process(0x130, b'')

    def test_native_speed_capture(self):
        client = Client()
        client.process(0x0E2, guid(24) + struct.pack('<IBf', 7, 1, 11.2))
        client.process(0x381, guid(24) + struct.pack('<If', 8, 17.5))
        self.assertAlmostEqual(client.speeds[0][2], 11.2, places=4)
        self.assertEqual(client.speeds[1], (0x381, 24, 17.5))
        with self.assertRaises(RuntimeError):
            client.process(0x381, guid(24))

    def test_setup_refuses_offline_target(self):
        runner = object.__new__(travel.TravelRunner)
        runner.guid, runner.known = 24, {24}
        runner.character = lambda _: {'online': 0}
        with self.assertRaises(RuntimeError):
            runner.setup(None, '.learn 458')

    def test_forward_levels_only(self):
        runner = object.__new__(travel.TravelRunner)
        runner.level = 20
        for level in (19, 20, 81):
            with self.assertRaises(RuntimeError):
                runner.advance(None, None, level)

    def test_login_refuses_other_accounts_and_unknown_guids(self):
        runner = object.__new__(travel.TravelRunner)
        runner.known = {13}
        runner.guid = 24
        for account, chosen in (('APV2A', 4), ('APV2E', 23), ('TEST', 12), ('APV2F', 13)):
            with self.assertRaises(RuntimeError), runner.login(account, guid=chosen):
                self.fail('unsafe login')


if __name__ == '__main__':
    unittest.main()
