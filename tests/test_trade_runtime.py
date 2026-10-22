"""Offline packet, ownership and no-transfer guards."""
from contextlib import redirect_stdout
import io
import json
import struct
import unittest
from unittest.mock import Mock, patch

import verify_trade_runtime as trade
from integration_inputs import require_inputs


def extended(entry=38):
    data = struct.pack('<BIIIII', 1, 0, 7, 7, 0, 0)
    for slot in range(7):
        data += bytes([slot]) + struct.pack('<III', entry if slot == 0 else 0, 0, 1 if slot == 0 else 0) + bytes(60)
    return data


class TradeTests(unittest.TestCase):
    def test_plan_never_connects(self):
        with patch.object(trade, 'probe_source') as probe, patch.dict('sys.modules', {'pymysql': None}), \
                redirect_stdout(io.StringIO()) as out:
            self.assertEqual(trade.main([]), 0)
        self.assertFalse(json.loads(out.getvalue())['network_without_run'])
        probe.assert_not_called()

    def test_credentials_before_source_or_network(self):
        with patch.dict(trade.os.environ, {}, clear=True), patch.object(trade, 'probe_source') as probe:
            with self.assertRaises(RuntimeError):
                trade.main(['--run'])
            probe.assert_not_called()

    def test_slot_zero_and_actual_backpack_mapping(self):
        self.assertEqual(trade.offer_packet(0, 15), bytes.fromhex('00ff0f'))
        self.assertEqual(trade.offer_packet(0, 38), bytes.fromhex('00ff26'))
        for bag, slot in ((255, 38), (1, 24), (0, 39), (0, -1), (False, 3)):
            with self.assertRaises(RuntimeError):
                trade.offer_packet(bag, slot)

    def test_send_guard_blocks_creation_acceptance_money_commands_and_wrong_targets(self):
        for opcode in (0x36, 0x11A, 0x11F, 0x95, 0x10F):
            with self.assertRaises(RuntimeError):
                trade.allowed_send(opcode, b'', 22)
        for opcode, payload, guid in ((0x3D, struct.pack('<Q', 13), 22),
                                      (0x116, struct.pack('<Q', 94), 22),
                                      (0x11D, bytes([6, 255, 38]), 22),
                                      (0x11D, bytes([0, 0, 38]), 22), (0x117, b'', 13)):
            with self.assertRaises(RuntimeError):
                trade.allowed_send(opcode, payload, guid)
        trade.allowed_send(0x116, struct.pack('<Q', 23), 22)
        trade.allowed_send(0x11C, b'', 22)

    def test_status_layouts_and_confounds_remain_distinct(self):
        self.assertEqual(trade.trade_status(struct.pack('<IQ', 1, 22)), dict(status=1, trader=22))
        self.assertEqual(trade.trade_status(struct.pack('<I', 3)), dict(status=3))
        self.assertEqual(trade.trade_status(struct.pack('<I', 10)), dict(status=10))
        self.assertEqual(trade.trade_status(struct.pack('<IIBI', 12, 1, 0, 0)),
                         dict(status=12, inventory_result=1, target=0, limit=0))
        for data in (b'', bytes(3), struct.pack('<I', 1), struct.pack('<I', 13), bytes(5)):
            with self.assertRaises(RuntimeError):
                trade.trade_status(data)

    def test_peer_offer_exact_parser(self):
        parsed = trade.trade_extended(extended())
        self.assertEqual(parsed['view'], 1)
        self.assertEqual(parsed['slots'][0]['entry'], 38)
        self.assertEqual([r['entry'] for r in parsed['slots'][1:]], [0] * 6)
        for data in (extended()[:-1], extended() + b'\0', bytes([2]) + extended()[1:],
                     extended()[:21] + bytes([6]) + extended()[22:]):
            with self.assertRaises(RuntimeError):
                trade.trade_extended(data)

    def evidence(self):
        require_inputs(trade.FUNDS_RUN, trade.FUNDS_RUN.parent.parent / 'summary.json')
        data = trade.FUNDS_RUN.read_bytes()
        summary = json.loads((trade.FUNDS_RUN.parent.parent / 'summary.json').read_text())
        return data, summary

    def test_exact_prior_pass_and_both_unique_creations(self):
        data, summary = self.evidence()
        self.assertEqual(set(trade.ownership(data, summary)), {22, 23})
        with self.assertRaises(RuntimeError):
            trade.ownership(data + b' ', summary)
        for key, value in (('run_sha256', 'bad'), ('offline_fixture_guids', [23]), ('result', {'event': 'FAIL'})):
            with self.assertRaises(RuntimeError):
                trade.ownership(data, dict(summary, **{key: value}))
        events = [json.loads(line) for line in data.splitlines()]
        creation = next(e for e in events if e.get('event') == 'login' and e.get('fresh') and e['guid'] == 22)
        duplicate = data + json.dumps(creation).encode() + b'\n'
        # Exercise uniqueness separately from the immutable-file hash check.
        with patch.object(trade, 'FUNDS_HASH', trade.digest(duplicate)):
            with self.assertRaisesRegex(RuntimeError, 'unique trusted creation'):
                trade.ownership(duplicate, dict(summary, run_sha256=trade.digest(duplicate)))

    def test_reuse_rejects_profile_and_binding_before_admission(self):
        require_inputs(trade.FUNDS_RUN, trade.FUNDS_RUN.parent.parent / 'summary.json')
        runner = object.__new__(trade.TradeRunner)
        runner.known, runner.names = set(), {}
        runner.account_row = Mock(return_value=dict(id=5, username='APV2D', email='wowpilago-fixture@invalid', security=0, online=0))
        profile = dict(guid=22, account=5, name='Apsqlkruenob', race=1, **{'class': 1}, level=1, online=0)
        for change in ({'guid': 13}, {'account': 1}, {'name': 'Other'}, {'level': 2}, {'online': 1}):
            runner.character = Mock(return_value=dict(profile, **change))
            with self.assertRaisesRegex(RuntimeError, 'profile'):
                runner.reuse()
            self.assertFalse(runner.known)
        runner.character = Mock(return_value=profile)
        runner.query = Mock(return_value=[])
        with self.assertRaisesRegex(RuntimeError, 'Binding'):
            runner.reuse()
        self.assertFalse(runner.known)

    def test_refusal_requires_handshake_and_positive_control(self):
        runner = object.__new__(trade.TradeRunner)
        a, b = Mock(), Mock()
        a.statuses, b.statuses = [], []
        with self.assertRaisesRegex(RuntimeError, 'target handshake'):
            runner.attempt(a, b, dict(slot=3, entry=38), 269, 15)
        a.send.assert_called_once_with(0x116, struct.pack('<Q', 23))

    def test_positive_offer_refusal_and_cancel_without_acceptance(self):
        for positive, refusal, success in ((True, 3, True), (False, 3, False), (True, 12, False)):
            runner = object.__new__(trade.TradeRunner)
            a, b = Mock(), Mock()
            for client in (a, b):
                client.statuses, client.updates, client.errors = [], [], []

            def send_a(opcode, payload=b''):
                if opcode == 0x116:
                    b.statuses.append(dict(status=1, trader=22))
                elif opcode == 0x11D and payload[2] == 3:
                    a.statuses.append(dict(status=7))
                    if positive:
                        b.updates.append(trade.trade_extended(extended()))
                elif opcode == 0x11D:
                    a.statuses.append(dict(status=refusal))
                elif opcode == 0x11C:
                    a.statuses.append(dict(status=3))
                    b.statuses.append(dict(status=3))

            def send_b(opcode, payload=b''):
                self.assertEqual(opcode, 0x117)
                a.statuses.append(dict(status=2))
                b.statuses.append(dict(status=2))
            a.send.side_effect, b.send.side_effect = send_a, send_b
            with redirect_stdout(io.StringIO()):
                if success:
                    runner.attempt(a, b, dict(slot=3, entry=38), 269, 15)
                else:
                    with self.assertRaises(RuntimeError):
                        runner.attempt(a, b, dict(slot=3, entry=38), 269, 15)
            self.assertNotIn(0x11A, [c.args[0] for c in a.send.call_args_list + b.send.call_args_list])
            if success:
                a.send.assert_any_call(0x11C)

    def test_client_keeps_shared_ping_and_login_guard(self):
        sock = Mock()
        authorize = Mock()
        client = trade.TradeClient(sock, authorize, 22)
        with redirect_stdout(io.StringIO()):
            client.send(0x3D, struct.pack('<Q', 22))
        authorize.assert_called_once()
        self.assertEqual(client.stay, trade.SmokeClient.stay.__get__(client))
        with self.assertRaises(RuntimeError):
            client.send(0x36, b'')
        self.assertEqual(sock.sendall.call_count, 1)


if __name__ == '__main__':
    unittest.main()
