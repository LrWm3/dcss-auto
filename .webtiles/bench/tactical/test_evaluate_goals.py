import unittest
from evaluate_goals import select_cases,MODEL_SHA

class BroaderGoalsTest(unittest.TestCase):
    def test_cohorts_exclude_used_cases_not_only_training(self):
        entries=[dict(id=str(i),seed=s,eligible=True) for i,s in enumerate(['1','2','1','3'])]
        reference=dict(train=[entries[0]],validation=[entries[1]])
        result=select_cases({'cases':entries},reference)
        self.assertEqual([e['id'] for e in result],['2','3'])
        self.assertEqual([e['cohort'] for e in result],['familiar_seed_new_case','unseen_seed'])
    def test_ineligible_excluded(self):
        self.assertEqual(select_cases({'cases':[dict(id='x',seed='1',eligible=False)]},
                                      dict(train=[],validation=[])),[])
    def test_model_is_pinned(self):
        self.assertEqual(len(MODEL_SHA),64)

if __name__=='__main__':unittest.main()
