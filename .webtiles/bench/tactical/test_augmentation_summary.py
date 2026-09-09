import unittest
from summarize_augmentation import summarize

class SummaryTest(unittest.TestCase):
    def rows(self):
        return [dict(case_id='v',family_id='f',policy=p,outcome='death',decisions=1,
            recipe=dict(hp_percent=80,rng_draws=1)) for p in ['withdraw:0','withdraw:1','defend:0','defend:1','pursue:0','pursue:1']]
    def test_missing_not_coverage_gap(self):
        r=summarize(self.rows()[:5],[dict(id='v',family_id='f')],{'f':{}})
        self.assertEqual(r['incomplete'],['v']);self.assertEqual(r['no_recovery'],[])
    def test_complete_gap(self):
        r=summarize(self.rows(),[dict(id='v',family_id='f')],{'f':{}})
        self.assertEqual(r['no_recovery'],['v'])
    def test_mixed_and_parent_flip(self):
        rows=self.rows();rows[0]['outcome']='recovered_quiet'
        r=summarize(rows,[dict(id='v',family_id='f',recipe=rows[0]['recipe'])],{'f':{'withdraw:0':'death'}})
        self.assertEqual(r['mixed_outcomes'],['v']);self.assertEqual(len(r['parent_flips']),1)
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):summarize(self.rows()*2,[],{})

if __name__=='__main__':unittest.main()
