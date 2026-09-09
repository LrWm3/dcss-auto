import copy
import unittest
from pathlib import Path
from unittest.mock import patch
from augmentation_dataset import classify, inventory, read, load_training
from augment_encounters import POLICIES
from bench import HERE

def rows():
    return [dict(option=o,outcome='recovered_quiet',evidence_verified=True) for o in POLICIES]

class DatasetTests(unittest.TestCase):
    def test_mixed_requires_real_death_and_success(self):
        r=rows();self.assertFalse(classify(r)['mixed'])
        r[0]['outcome']='death';self.assertTrue(classify(r)['mixed'])
        for outcome in ('masked','harness_error','budget_truncated','unresolved_stall','no_turn_stall'):
            r[0]['outcome']=outcome;self.assertFalse(classify(r)['mixed'])
    def test_missing_duplicate_or_unaudited_rejected(self):
        r=rows();r[0]['outcome']='death'
        self.assertFalse(classify(r[:-1])['complete'])
        self.assertFalse(classify(r+[r[0]])['complete'])
        r[-1]['evidence_verified']=False;self.assertFalse(classify(r)['mixed'])
    def test_all_fail_not_selected(self):
        r=rows()
        for x in r:x['outcome']='death'
        self.assertTrue(classify(r)['complete']);self.assertFalse(classify(r)['mixed'])
    def test_masks_not_failures_but_do_not_prevent_mixed(self):
        r=rows();r[0]['outcome']='masked';r[1]['outcome']='death'
        c=classify(r);self.assertTrue(c['mixed']);self.assertEqual(c['failing'],[POLICIES[1]])
        r[0]['evidence_verified']=False;self.assertFalse(classify(r)['mixed'])
    def test_current_inventory_keeps_seed_families(self):
        es=inventory(read(HERE/'augmentation-all-v1.json'));groups={}
        for e in es:
            groups.setdefault(e['seed'],set()).add(e['split'])
            if e['seed'].startswith('830290'):self.assertEqual(e['split'],'evaluation_only')
            if e['seed']=='83017004':self.assertEqual(e['split'],'test')
            if e['seed']=='83017003':self.assertEqual(e['split'],'validation')
        self.assertTrue(all(len(g)==1 for g in groups.values()))
        self.assertTrue(any(not e['eligible'] for e in es))

    def fixture(self):
        return {'manifest.json':dict(sources={},inputs={},engine_sha256='h',
                    config={'partitions':'partitions.json'}),
            'training-index.json':dict(manifest_sha256='h',labels_sha256='h',rows_sha256='h',
                cases=[dict(id='case',case='/case',seed='1',split_group='1',
                            save_sha256='h',rc_sha256='h')]),
            'partitions.json':dict(train=['1'],validation=['2'],test=['3']),
            'training-rows.json':[dict(case_id='case',seed='1',split='train',
                outcome='death',evidence_verified=True,trace='/trace',trace_sha256='h')]}

    def load_fixture(self,d):
        with patch('augmentation_dataset.read',side_effect=lambda p:d[Path(p).name]), \
             patch('augmentation_dataset.sha',return_value='h'):
            return load_training('/dataset')

    def test_training_loader_allows_verified_training_rows(self):
        self.assertEqual(len(self.load_fixture(self.fixture())),1)

    def test_training_loader_rejects_held_out_case_or_row(self):
        for seed in ('2','3','99'):
            d=self.fixture();d['training-index.json']['cases'][0].update(seed=seed,split_group=seed)
            with self.assertRaises(ValueError):self.load_fixture(d)
            d=self.fixture();d['training-rows.json'][0]['seed']=seed
            with self.assertRaises(ValueError):self.load_fixture(d)

    def test_training_loader_rejects_stall_or_missing_audit(self):
        for change in ({'outcome':'unresolved_stall'},{'evidence_verified':False},{'split':'test'}):
            d=self.fixture();d['training-rows.json'][0].update(change)
            with self.assertRaises(ValueError):self.load_fixture(d)

    def test_training_loader_rejects_changed_trace(self):
        d=self.fixture();d['training-rows.json'][0]['trace_sha256']='changed'
        with self.assertRaises(ValueError):self.load_fixture(d)

if __name__=='__main__':unittest.main()
