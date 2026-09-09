import unittest
from evaluate_rich_holdout import summarize


class HoldoutTests(unittest.TestCase):
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
