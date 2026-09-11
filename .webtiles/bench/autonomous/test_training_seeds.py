import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from training_seeds import plan_cycle
from data_split import held_out_seed


class TrainingSeedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/'replay').mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def result(self,name,seed,score,**extra):
        (self.root/'replay'/f'{name}.result.json').write_text(json.dumps({
            'seed':seed,'score':score,'terminal':True,'data_role':'training',**extra}))

    def test_lowest_previous_training_score_including_cutoff(self):
        self.result('cycle-0004-0','10',40)
        self.result('cycle-0004-1','11',7,terminal=False,truncated=True,score_status='cutoff_official')
        self.result('cycle-0004-2','12',20)
        self.result('cycle-0004-counterfactual','13',0)
        self.result('cycle-0003-0','14',1)
        plan=plan_cycle(self.root,5)
        self.assertEqual([e['role'] for e in plan['episodes']],['fresh','fresh','previous_lowest'])
        self.assertEqual(plan['episodes'][2]['seed'],'11')
        self.assertEqual(plan['episodes'][2]['previous_score'],7)
        self.assertFalse(any(held_out_seed(e['seed']) for e in plan['episodes']))
        self.assertEqual(len({e['seed'] for e in plan['episodes']}),3)

    def test_resume_is_frozen_and_next_cycle_gets_fresh_rng_and_seeds(self):
        self.result('cycle-0000-0','10',40)
        first=plan_cycle(self.root,1)
        with patch('training_seeds.secrets.randbits',side_effect=AssertionError('must reuse manifest')):
            self.assertEqual(plan_cycle(self.root,1),first)
        for i,e in enumerate(first['episodes']):
            self.result(f'cycle-0001-{i}',e['seed'],[5,20,40][i])
        second=plan_cycle(self.root,2)
        self.assertEqual(second['episodes'][2]['seed'],first['episodes'][0]['seed'])
        self.assertFalse({e['seed'] for e in first['episodes']} & {e['seed'] for e in second['episodes'][:2]})
        self.assertFalse({e['exploration_seed'] for e in first['episodes']} & {e['exploration_seed'] for e in second['episodes']})

    def test_crashes_and_held_out_results_cannot_select_retry(self):
        self.result('cycle-0000-0','10',0,error='crash')
        self.result('cycle-0000-1',str(0xD << 60),0,data_role='confirmation')
        self.assertEqual([e['role'] for e in plan_cycle(self.root,1)['episodes']],['fresh']*3)

    def test_collector_receives_frozen_exploration_rng(self):
        from train_crawl_agent import collect_parallel
        calls=[]
        def actor(*args,**kwargs):
            calls.append((args[1],kwargs['exploration_seed']))
            return {'seed':args[1],'steps':1}
        (self.root/'metrics').mkdir()
        with patch('train_crawl_agent.run_episode',side_effect=actor), patch('train_crawl_agent.storage.maintain'):
            collect_parallel(self.root,['1','2','3'],'cycle-0000',3,1,None,.1,False,
                             exploration_seeds=[101,102,103])
        self.assertEqual(sorted(calls),[('1',101),('2',102),('3',103)])


if __name__ == '__main__':
    unittest.main()
