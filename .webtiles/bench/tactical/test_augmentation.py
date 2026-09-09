import unittest
from augment_encounters import validate_recipe,wrapper

class AugmentationTest(unittest.TestCase):
    def test_valid(self):
        validate_recipe(dict(hp_percent=80,rng_draws=17))
    def test_invalid_values(self):
        for hp,rng in [(0,1),(101,1),(80,-1),(80,100001),(True,1),(80,1.5)]:
            with self.subTest(hp=hp,rng=rng),self.assertRaises(ValueError):
                validate_recipe(dict(hp_percent=hp,rng_draws=rng))
    def test_extra_field_rejected(self):
        with self.assertRaises(ValueError):validate_recipe(dict(hp_percent=80,rng_draws=1,seed=1))
    def test_one_shot_before_ready(self):
        s=wrapper(dict(hp_percent=80,rng_draws=17))
        self.assertIn('you.tactical_augment(80, 17)',s)
        self.assertLess(s.index('augmentation_applied = true'),s.index('augmentation_ready()'))

if __name__=='__main__':unittest.main()
