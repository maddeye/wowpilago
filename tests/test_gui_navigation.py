import math
import unittest

from gui_navigation import chat, hold, parse_probe, turn_delta


class NavigationTests(unittest.TestCase):
    def test_shortest_turn_wraps(self):
        self.assertAlmostEqual(turn_delta(6.2, .1), 2 * math.pi - 6.1)
        self.assertAlmostEqual(turn_delta(.1, 6.2), 6.1 - 2 * math.pi)
        self.assertEqual(turn_delta(1, 1), 0)

    def test_reject_unbounded_input(self):
        for key, seconds in [('w', 6), ('w', 0), ('Return', 1)]:
            with self.assertRaises(ValueError):
                hold(key, seconds)
        with self.assertRaises(ValueError):
            chat('/run x\n/logout')
        with self.assertRaises(ValueError):
            chat('x' * 256)

    def test_only_fresh_probe(self):
        self.assertEqual(parse_probe('NAVold 1 0 0\nNAVnew 2.64 0 0', 'NAVnew'), (2.64, 0, 0))
        with self.assertRaises(ValueError):
            parse_probe('NAVold 1 0 0', 'NAVnew')


if __name__ == '__main__':
    unittest.main()
