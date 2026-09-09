import unittest
from evaluate_rich_holdout import summarize, same_original


class HoldoutTests(unittest.TestCase):
    def test_original_projection_allows_only_added_fields(self):
        old=dict(hp=10,turn=5,monsters={},messages={})
        rich={**old,'player':{'xl':2},'known':{},'position':{'x':1,'y':1}}
        self.assertTrue(same_original(old,rich))
        self.assertFalse(same_original(old,{**rich,'hp':9}))
        del rich['turn']
        self.assertFalse(same_original(old,rich))

    def test_unknowns_excluded_from_paired_comparison(self):
        def family(outcomes):
            return dict(split='test', status='complete', rows=[
                dict(evaluator=n, outcome=o, evidence_verified=o!='unresolved_stall')
                for n,o in zip(('candidate','pursue_no_berserk','pursue_berserk'),outcomes)])
        report=summarize([family(['recovered_quiet','death','recovered_quiet']),
                          family(['unresolved_stall','death','death'])])
        self.assertEqual(report['all']['comparable'],1)
        self.assertEqual(report['all']['excluded'],1)
        self.assertEqual(report['test']['paired_outcomes']['pursue_no_berserk'],{'death':1})
        self.assertEqual(report['evaluation_only']['encounters'],0)


if __name__=='__main__': unittest.main()
