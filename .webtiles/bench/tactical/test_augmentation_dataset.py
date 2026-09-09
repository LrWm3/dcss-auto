import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from augmentation_dataset import classify, inventory, read, load_training, export, compatible_cache, reuse_families, policy_trial, family
from run_goals import SOURCES
from verify_resume import normalized
from train_encounters import write
from augment_encounters import POLICIES
from bench import HERE

def rows():
    return [dict(option=o,outcome='recovered_quiet',evidence_verified=True) for o in POLICIES]

class DatasetTests(unittest.TestCase):
    def test_policy_retry_uses_separate_attempt_and_preserves_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);worker=root/'worker';worker.mkdir()
            (worker/'terminal.txt').write_text("lair.des:2079: Map 'regret_index_lairdec_grave_grove' has no (possible) exits")
            old=dict(outcome='harness_error',decisions=0,worker=str(worker),split='train')
            with patch('augmentation_dataset.run',return_value=dict(outcome='death',decisions=3)) as run:
                result=policy_trial({'id':'v'},root/'case',root/'retry','pursue:1',600,old)
            self.assertEqual(run.call_args.args[2],root/'retry'/'attempt-1')
            self.assertEqual(result['startup_attempts'],[old])
            self.assertEqual(result['split'],'train')

    def test_cached_gameplay_result_is_not_retried(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);case=root/'case';case.mkdir();work=root/'family';work.mkdir()
            write(work/'family.json',dict(variants=[dict(id='family/v',case=str(case),rows=rows())]))
            write(case/'case.json',dict(save_sha256='h',rc_sha256='h'))
            with patch('augmentation_dataset.sha',return_value='h'),patch('augmentation_dataset.run') as run:
                family(dict(id='family',seed='1'),{'steps':600},root)
            run.assert_not_called()

    def test_reuse_creates_nested_family_output(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);origin=base/'old';root=base/'new';root.mkdir()
            ident='collection/encounter';(origin/ident).mkdir(parents=True)
            (origin/ident/'family.json').touch()
            workers=[]
            for i in range(2):
                w=base/str(i);w.mkdir();workers.append(str(w))
                # A transition log has one compact JSON object per line.
                (w/'transitions.jsonl').write_text(json.dumps(dict(observation={'hp':1},next_observation={'terminal':'death'}))+'\n')
            e=dict(id=ident,seed='1',split='train')
            m=dict(config={'recipes':[{}]},entries=[e],inputs={},engine_sha256='a',parent_engine_sha256='b',
                sources={n:'h' for n in SOURCES+('augment_encounters.py',)})
            f=dict(id=ident,seed='1',split='train',status='generated',
                variants=[dict(replay_verified=True,recipe={},workers=workers,trace_sha256=['h','h'],rows=[{}]*6)],
                neutral=dict(passed=True,reference='/ref',reference_sha256='h',worker='/worker',trace_sha256='h'))
            actual_read=read
            with patch('augmentation_dataset.read',side_effect=lambda p:m if Path(p).name=='manifest.json' else f), \
                 patch('augmentation_dataset.sha',return_value='h'):
                self.assertEqual(reuse_families(origin,root,m),[ident])
            self.assertEqual(actual_read(root/ident/'family.json')['id'],ident)
    def test_death_provenance_not_gameplay(self):
        self.assertEqual(normalized({'terminal':'death'}),normalized(dict(
            terminal='death',evidence='/private/morgue',evidence_sha256='different')))
        self.assertNotEqual(normalized({'terminal':'death'}),normalized({'hp':1}))
        self.assertNotEqual(normalized({'terminal':'death','turn':10}),
                            normalized({'terminal':'death','turn':11}))

    def test_reuse_rejects_gameplay_or_input_changes(self):
        m=dict(config={},entries=[],inputs={},engine_sha256='a',parent_engine_sha256='b',
               sources={n:'h' for n in SOURCES+('augment_encounters.py','verify_resume.py','augmentation_dataset.py')})
        n=copy.deepcopy(m);n['sources']['verify_resume.py']='new';compatible_cache(m,n)
        n['sources']['augmentation_dataset.py']='new';compatible_cache(m,n)
        for key in ('config','entries','inputs','engine_sha256','parent_engine_sha256'):
            n=copy.deepcopy(m);n[key]='changed'
            with self.assertRaises(ValueError):compatible_cache(m,n)
        for key in SOURCES+('augment_encounters.py',):
            n=copy.deepcopy(m);n['sources'][key]='changed'
            with self.assertRaises(ValueError):compatible_cache(m,n)
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

    def test_export_excludes_mixed_heldout_and_unassigned_families(self):
        for split in ('validation','test','evaluation_only','unassigned'):
            r=rows();r[0]['outcome']='death'
            v=dict(id='variant',recipe={},case='/must-not-read',replay_verified=True,rows=r)
            f=dict(id='family',seed='2',split=split,status='generated',variants=[v])
            with tempfile.TemporaryDirectory() as d, \
                 patch('augmentation_dataset.verify_result',side_effect=lambda r:r):
                root=Path(d);write(root/'manifest.json',{})
                summary=export(root,[f])
                self.assertEqual(summary['mixed_variants'],1)
                self.assertEqual(summary['training_cases'],0)
                self.assertEqual(read(root/'training-rows.json'),[])

if __name__=='__main__':unittest.main()
