import unittest
from retrain_augmented_goals import choice, evaluate


def rows():
    options=[g+':'+str(b) for g in ('withdraw','defend','pursue') for b in (0,1)]
    return [dict(case_id='a',seed='1',split='validation',option=o,
                 outcome='death' if o=='pursue:1' else 'recovered_quiet',
                 features={'bias':1},available=options[2:]) for o in options]


class RetrainTests(unittest.TestCase):
    def test_respects_masks_and_stable_ties(self):
        self.assertEqual(choice({'withdraw:1':{'bias':100}},rows()),'defend:0')

    def test_rejects_inconsistent_initial_state(self):
        r=rows();r[-1]['features']={'bias':2}
        with self.assertRaises(ValueError):choice({},r)

    def test_evaluates_losses_without_filtering(self):
        selections,summary=evaluate({'pursue:1':{'bias':1}}, {}, rows())
        self.assertEqual(summary['validation']['candidate'],{'death':1})
        self.assertEqual(summary['validation']['baseline'],{'recovered_quiet':1})
        self.assertEqual(len(selections),1)


if __name__=='__main__':unittest.main()
