import unittest
from unittest.mock import patch
from visit_memory import initial, advance, features


def state(x=0, y=0, level='D:1'):
    return {'player': {'x': x, 'y': y}, 'level': level, 'known': {'0:0': {}}}


class VisitMemoryTests(unittest.TestCase):
    def test_backtracking_is_visible_not_banned(self):
        a = state(); a['visit_memory'] = initial(a)
        b = state(1); b['visit_memory'] = advance(a, {'kind': 'MOVE', 'dx': 1}, b)
        c = state(); c['visit_memory'] = advance(b, {'kind': 'MOVE', 'dx': -1}, c)
        self.assertEqual(c['visit_memory']['tiles']['0:0'][0], 2)
        self.assertEqual(features(c, {'kind': 'MOVE', 'dx': 1})[1], 1)
        self.assertEqual(features(c, {'kind': 'MOVE', 'dx': -1})[1], 0)

    def test_stationary_actions_do_not_invent_arrivals(self):
        a = state(); a['visit_memory'] = initial(a)
        b = state(); m = advance(a, {'kind': 'REST'}, b)
        self.assertEqual(m['tiles']['0:0'][0], 1)
        self.assertEqual(m['since_discovery'], 1)

    def test_level_change_resets_memory(self):
        a = state(); a['visit_memory'] = initial(a)
        b = state(level='D:2')
        self.assertEqual(advance(a, {'kind': 'TAKE_STAIRS_DOWN'}, b), initial(b))

    def test_ambiguous_motion_resets_memory(self):
        a = state(); a['visit_memory'] = initial(a)
        with patch('observation_history.observed_displacement', return_value=None):
            self.assertEqual(advance(a, {'kind': 'MOVE'}, a), initial(a))

    def test_discovery_resets_age(self):
        a = state(); a['visit_memory'] = initial(a)
        a['visit_memory']['since_discovery'] = 40
        b = state(1); b['known']['1:0'] = {}
        self.assertEqual(advance(a, {'kind': 'MOVE', 'dx': 1}, b)['since_discovery'], 0)

    def test_missing_memory_is_explicit(self):
        self.assertEqual(features({}, {}), [0.] * 8)
