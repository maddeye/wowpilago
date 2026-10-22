"""Behavior checks for the bounded class-system runner, no live connections."""
import contextlib
import io
import struct
import unittest
from unittest.mock import patch

from verify_class_systems import (ClassRunner, expected_points, fixture_guard, items,
                                 main, talent_packet)
from verify_runtime import MARKER


class ClassSystemTests(unittest.TestCase):
    def test_talent_schedule_early_and_later(self):
        self.assertEqual([expected_points(n, 0) for n in (1, 9, 10, 14, 15, 20, 70, 80)],
                         [0, 0, 1, 5, 5, 9, 49, 59])
        self.assertEqual(expected_points(1, 12), 0)
        self.assertEqual(expected_points(14, 12), 5)
        self.assertEqual(expected_points(15, 12), 6)
        self.assertEqual(expected_points(80, 1), 60)
        self.assertEqual(expected_points(80, 12), 71)
        for level in (0, 81, True):
            with self.assertRaises(RuntimeError):
                expected_points(level, 0)

    def test_account_guards_and_slots(self):
        row = dict(username='APV2C', email=MARKER, security=0, online=0)
        fixture_guard('APV2C', row, 9)
        for account, changes, count in [('APV2A', {}, 0), ('APV2C', {'online': 1}, 0),
                                        ('APV2C', {'security': 3}, 0),
                                        ('APV2C', {'email': ''}, 0), ('APV2C', {}, 10)]:
            with self.assertRaises(RuntimeError):
                fixture_guard(account, row | changes, count)
        fixture_guard('TEST', dict(username='TEST', security=3, online=0), 7, setup=True)

    def test_real_talent_packet_and_invalid_actions(self):
        self.assertEqual(talent_packet(130, 4), struct.pack('<II', 130, 4))
        for talent, rank in ((0, 0), (130, -1), (130, 5), (130, True)):
            with self.assertRaises(RuntimeError):
                talent_packet(talent, rank)

    def test_queue_is_append_only_and_preserves_duplicate_unlocks(self):
        runner = object.__new__(ClassRunner)
        runner.codes = [919100001]
        class Store:
            def receive(self, index, records):
                self.received = index, records
                return True
        runner.store = Store()
        with contextlib.redirect_stdout(io.StringIO()):
            runner.queue(919100020, 919100020)
        self.assertEqual(runner.store.received, (1, items([919100020, 919100020])))
        self.assertEqual(runner.codes, [919100001, 919100020, 919100020])
        with self.assertRaises(RuntimeError):
            runner.queue()

    def test_forward_only_setup(self):
        runner = object.__new__(ClassRunner)
        runner.level, runner.cap, runner.guid = 20, 30, 12
        runner.names = {12: 'Apfixture'}
        calls = []
        runner.command = calls.append
        for target in (19, 20, 31):
            with self.assertRaises(RuntimeError):
                runner.advance(target)
        runner.advance(26)
        self.assertEqual(calls, ['.levelup Apfixture 6'])
        self.assertEqual(runner.level, 26)

    def test_default_plan_has_no_runtime_access(self):
        with patch('verify_class_systems.ClassRunner') as runner, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([]), 0)
            runner.assert_not_called()


if __name__ == '__main__':
    unittest.main()
