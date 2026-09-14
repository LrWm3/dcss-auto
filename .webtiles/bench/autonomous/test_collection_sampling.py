import unittest
from collection_sampling import capture_reason, select_snapshots


class CollectionSamplingTests(unittest.TestCase):
    def test_no_loop_still_captures(self):
        self.assertEqual(capture_reason({}, 0), 'periodic')
        self.assertEqual(capture_reason({'safe': True}, 20), 'ordinary_exploration')
        self.assertEqual(capture_reason({'monsters': [{}]}, 40), 'periodic')
        self.assertIsNone(capture_reason({'safe': True}, 21, ordinary_saved=True))

    def test_recent_predeath_and_ordinary_selected(self):
        records = [{'path': str(i), 'step': i, 'reason': reason} for i,reason in
                   ((0,'periodic'), (20,'ordinary_exploration'), (40,'periodic'),(80,'periodic'))]
        selected = select_snapshots(records, 'death', 93)
        self.assertEqual([s['step'] for s in selected], [20,80])
        self.assertEqual(selected[-1]['decisions_before_death'], 13)
        self.assertNotIn('selection_reason', records[-1])

    def test_immediate_death_has_fallback(self):
        r = [{'path': 'start', 'step': 0, 'reason': 'periodic'}]
        self.assertEqual(len(select_snapshots(r, 'death', 1)), 1)

    def test_loop_still_captured(self):
        self.assertEqual(capture_reason({}, 23, loop=True), 'loop')
