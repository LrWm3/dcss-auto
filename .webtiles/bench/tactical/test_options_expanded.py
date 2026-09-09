import json
import tempfile
import unittest
from pathlib import Path
from train_options_expanded import labels_hash, metrics, progress, same_checkpoint, cached_rows


class ExpandedTests(unittest.TestCase):
    def test_progress_distinguishes_survival_ascent_and_descent(self):
        self.assertFalse(progress('D:2','D:2')['floor_changed'])
        self.assertTrue(progress('D:2','D:3')['deeper_same_branch'])
        self.assertFalse(progress('D:2','D:1')['deeper_same_branch'])
        self.assertTrue(progress('D:2','D:1')['floor_changed'])
        self.assertFalse(progress('D:2',None)['floor_changed'])
        self.assertFalse(progress('D:9','Lair:1')['deeper_same_branch'])

    def test_metric_does_not_count_stall_or_budget_as_success(self):
        rows=[dict(audited_credit=c,**progress('D:2',f)) for c,f in
              [(1,'D:3'),(1,'D:2'),(0,'D:2'),(-1,None)]]
        m=metrics(rows)
        self.assertEqual((m['positive'],m['neutral'],m['deaths']),(2,1,1))
        self.assertEqual(m['deeper_same_branch'],1)
        self.assertEqual(m['recovered_without_floor_change'],1)

    def test_label_digest_detects_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'a').mkdir();p=root/'a/option-transition.json'
            p.write_text('{}');before=labels_hash(root)
            p.write_text('{"credit":1}')
            self.assertNotEqual(labels_hash(root),before)

    def test_checkpoint_identity_rejects_seed_or_save_changes(self):
        a=dict(seed='1',save_sha256='a',rc_sha256='b',engine_sha256='c')
        self.assertTrue(same_checkpoint(a,a))
        self.assertFalse(same_checkpoint(a,dict(a,seed='2')))
        self.assertFalse(same_checkpoint(a,dict(a,save_sha256='x')))

    def test_real_cached_training_matrix_is_complete_for_existing_labels(self):
        from train_encounters import load_cases
        cfg=json.loads(Path(__file__).with_name('options-expanded-v1.json').read_text())
        (train,validation),_=load_cases(cfg)
        cache,_=cached_rows(cfg['caches'],train,cfg)
        self.assertEqual(len(cache),54)
        self.assertEqual(len(train)*4-len(cache),54)
        self.assertFalse({e['id'] for e in validation}&{key[0] for key in cache})


if __name__=='__main__': unittest.main()
