import unittest
from run_direction_cycle import advance_hook


class DirectionCycleTests(unittest.TestCase):
    def test_only_action_rng_hook_changes(self):
        source='you.tactical_augment(100,0)\nif not action_rng_applied then\n    you.tactical_augment(100,0)\nend'
        changed=advance_hook(source,5)
        self.assertTrue(changed.startswith('you.tactical_augment(100,0)'))
        self.assertEqual(changed.count('you.tactical_augment(100,5)'),1)

    def test_missing_or_duplicate_hook_rejected(self):
        hook='if not action_rng_applied then\n you.tactical_augment(100,0)\n'
        for source in ('you.tactical_augment(100,0)',hook+hook):
            with self.assertRaises(ValueError):advance_hook(source,3)


if __name__=='__main__':unittest.main()
