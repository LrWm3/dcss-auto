import tempfile
import unittest
from pathlib import Path
from bench import Environment,NAME

class DeathRecordTest(unittest.TestCase):
    def check(self,content,filename=None):
        with tempfile.TemporaryDirectory() as d:
            e=Environment(d,seed='123');e.work=Path(d);e.state={'turn':100}
            (e.work/'morgue').mkdir()
            (e.work/'morgue'/(filename or f'morgue-{NAME}-date.txt')).write_text(content)
            return e.death_record()
    def morgue(self):
        return f'Game seed: 123 (custom seed)\n2398 {NAME} the Cleaver (level 9, 0/79 HPs)\nSuccumbed to poison\nTurns: 101\n'
    def test_current_death_morgue(self):
        self.assertEqual(self.check(self.morgue())['terminal'],'death')
    def test_overkill_death(self):
        self.assertEqual(self.check(self.morgue().replace('0/79','-12/79'))['terminal'],'death')
        self.assertIsNone(self.check(self.morgue().replace('0/79','12/79')))
    def test_wrong_seed(self):
        self.assertIsNone(self.check(self.morgue().replace('seed: 123','seed: 124')))
    def test_stale_turn(self):
        self.assertIsNone(self.check(self.morgue().replace('Turns: 101','Turns: 99')))
    def test_character_dump_not_death(self):
        self.assertIsNone(self.check(self.morgue(),NAME+'.txt'))
    def test_living_or_partial_record(self):
        self.assertIsNone(self.check(self.morgue().replace('0/79','1/79')))
        self.assertIsNone(self.check('You die...'))

if __name__=='__main__':unittest.main()
