import copy
import unittest
from dataset_splits import enforce,partition_map


def entries():
    return [dict(id=str(i),seed='8301700'+str(i),eligible=True) for i in range(1,6)]


class SplitTests(unittest.TestCase):
    def test_expands_cases_and_records_provenance(self):
        cfg={'evaluation_mode':'held_out'};enforce(cfg,entries())
        self.assertEqual(cfg['train_cases'],['1','2','5'])
        self.assertEqual(cfg['eval_cases'],['3'])
        self.assertEqual(cfg['split_provenance']['evaluation_partition'],'validation')

    def test_blocks_test_and_validation_training(self):
        for id_ in ('3','4'):
            with self.assertRaisesRegex(ValueError,'not train'):
                enforce(dict(evaluation_mode='held_out',train_cases=[id_]),entries())

    def test_blocks_test_or_train_as_validation(self):
        for id_ in ('4','5'):
            with self.assertRaisesRegex(ValueError,'not validation'):
                enforce(dict(evaluation_mode='held_out',eval_cases=[id_]),entries())

    def test_no_in_sample_bypass(self):
        with self.assertRaisesRegex(ValueError,'not in_sample'):
            enforce(dict(evaluation_mode='in_sample'),entries())

    def test_recaptures_inherit_seed_partition(self):
        rows=entries();rows.append(dict(rows[-1],id='recaptured'))
        cfg=dict(evaluation_mode='held_out');enforce(cfg,rows)
        self.assertIn('recaptured',cfg['train_cases'])

    def test_unknown_and_duplicate_seeds_rejected(self):
        rows=entries()+[dict(id='unknown',seed='999',eligible=True)]
        with self.assertRaisesRegex(ValueError,'Unassigned'):
            enforce(dict(evaluation_mode='held_out'),rows)
        with self.assertRaisesRegex(ValueError,'multiple'):
            partition_map(dict(train=['1'],validation=['1'],test=['2']))

    def test_disjoint_no_missing_cases(self):
        rows=entries();before=copy.deepcopy(rows)
        cfg=dict(evaluation_mode='held_out');enforce(cfg,rows)
        self.assertEqual(rows,before)
        self.assertEqual(len(set(cfg['train_cases']) & set(cfg['eval_cases'])),0)


if __name__=='__main__': unittest.main()
