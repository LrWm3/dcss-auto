import unittest
from summarize_goal_evaluation import summarize

def rows():
    return [dict(case_id='c',seed='s',cohort='unseen_seed',policy=p,option=p if p!='selector' else 'defend:0',
        outcome='death',decisions=4,worker='/unused') for p in
        ['selector','withdraw:0','withdraw:1','defend:0','defend:1','pursue:0','pursue:1']]

class GoalSummaryTest(unittest.TestCase):
    def test_selection_miss(self):
        r=rows();r[-1]['outcome']='recovered_quiet'
        f=summarize(r)['failures'][0]
        self.assertEqual(f['kind'],'selection_miss');self.assertEqual(f['successful_alternatives'],['pursue:1'])
    def test_unresolved_and_masked_not_success(self):
        r=rows();r[-1]['outcome']='unresolved_stall';r[-2]['outcome']='masked'
        self.assertEqual(summarize(r)['failure_types'],{'controller_coverage_gap':1})
    def test_harness_error_not_proven_coverage_gap(self):
        r=rows();r[-1]['outcome']='harness_error'
        self.assertEqual(summarize(r)['failure_types'],{'incomplete_or_error':1})
    def test_selector_error_not_assumed_losing_choice(self):
        r=rows();r[0]['outcome']='harness_error';r[-1]['outcome']='recovered_quiet'
        f=summarize(r)['failures'][0]
        self.assertEqual(f['kind'],'incomplete_or_error')
        self.assertEqual(f['successful_alternatives'],['pursue:1'])
    def test_repeat_difference_exposed(self):
        r=rows();r[3]['outcome']='recovered_quiet'
        self.assertEqual(len(summarize(r)['repeat_mismatches']),1)
    def test_duplicate_rejected(self):
        r=rows()
        with self.assertRaises(ValueError):summarize(r+[r[0]])

if __name__=='__main__':unittest.main()
