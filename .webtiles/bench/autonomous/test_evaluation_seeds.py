import json
import tempfile
import unittest
from pathlib import Path

from data_split import SCREEN_PREFIX, assert_training_seed, held_out_seed
from evaluation_seeds import POOL_VERSION, screen_seed_plan


class EvaluationSeedTests(unittest.TestCase):
    def test_rotates_and_covers_default_pool(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            all_seeds = []
            for cycle in range(10):
                seeds, path = screen_seed_plan(root, cycle, 5)
                self.assertEqual(len(set(seeds)), 5)
                self.assertTrue(path.exists())
                self.assertEqual(json.loads(path.read_text())["version"], POOL_VERSION)
                self.assertTrue(all(held_out_seed(seed) for seed in seeds))
                all_seeds.extend(seeds)
            self.assertEqual(len(set(all_seeds)), 50)
            self.assertEqual(screen_seed_plan(root, 0, 5)[0], all_seeds[:5])

    def test_plan_is_frozen(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screen_seed_plan(root, 0, 5)
            with self.assertRaises(ValueError):
                screen_seed_plan(root, 0, 4)

    def test_screen_namespace_is_training_quarantined(self):
        self.assertEqual(int("13835058055282163713") >> 60, SCREEN_PREFIX)
        seed = str((SCREEN_PREFIX << 60) | 1)
        self.assertTrue(held_out_seed(seed))
        with self.assertRaises(ValueError):
            assert_training_seed(seed)


if __name__ == "__main__":
    unittest.main()
