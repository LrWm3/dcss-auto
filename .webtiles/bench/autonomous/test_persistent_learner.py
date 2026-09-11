import json
from pathlib import Path
import sys
import tempfile
import unittest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from learner import parent_for_cycle, prepare_candidate, finish_candidate, balanced_sample
from model import ActionValueModel, save_model, load_model
from training_seeds import plan_cycle
from train_model import train_counterfactual_preferences, rows_from_replay


class PersistentLearnerTests(unittest.TestCase):
    def test_rejection_restart_and_optimizer_continuity(self):
        torch.set_num_threads(1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            champion = root / 'V0.pt'
            save_model(champion, ActionValueModel())
            state = {'schema': 'crawl-general-v1', 'actions': [{'kind':'WAIT'}, {'kind':'MOVE','dx':1}]}
            rows = [{'observation': state, 'teacher_action_index':0, 'action_index':0,
                     'return':1, 'episode_seed':'1', 'behavior_probability':0.5}]
            rows += [{'observation':state, 'action_index':i, 'return':v,
                      'comparison_id':'first',
                      'return_protocol':'official_score_at_terminal_or_fixed_horizon_v2'} for i,v in enumerate([1,10])]
            first = root / 'candidate0.pt'
            parent = parent_for_cycle(root, 0, champion)
            prepare_candidate(parent, first, rows, 0)
            finish_candidate(root, 0, first, rows)
            # No promotion: V0 remains champion, but next learner uses candidate0.
            self.assertEqual(parent_for_cycle(root, 1, champion), first)
            self.assertEqual(parent_for_cycle(root, 1, champion), first)
            second = root / 'candidate1.pt'
            prepare_candidate(first, second, rows, 1)
            finish_candidate(root, 1, second, rows)
            a = load_model(first)[1]['metadata']['optimizer_states']
            b = load_model(second)[1]['metadata']['optimizer_states']
            for name in ('actor_return','critic','preferences'):
                self.assertGreater(b[name]['state'][0]['step'], a[name]['state'][0]['step'])
            self.assertFalse(all(torch.equal(v, load_model(second)[0].state_dict()[k])
                                 for k,v in load_model(first)[0].state_dict().items()))

    def test_diverse_batch_and_frozen_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'replay').mkdir()
            (root/'replay'/'cycle-0000-0.result.json').write_text(json.dumps(
                {'seed':'123','score':2,'terminal':True}))
            plan = plan_cycle(root,1,8)
            self.assertEqual(len(plan['episodes']),8)
            self.assertEqual(sum(e['role']=='fresh' for e in plan['episodes']),7)
            self.assertEqual(plan_cycle(root,1,12),plan)

    def test_seed_balancing_and_comparison_isolation(self):
        rows = [{'episode_seed':'1'}]*100 + [{'episode_seed':'2'}]*3
        sample = balanced_sample(rows,6,0)
        self.assertEqual(sum(r['episode_seed']=='2' for r in sample),3)
        state = {'actions':[{'kind':'WAIT'},{'kind':'MOVE','dx':1}]}
        rows = [{'observation':state,'action_index':i,'return':v,'comparison_id':str(i)}
                for i,v in enumerate([1,10])]
        self.assertEqual(train_counterfactual_preferences(ActionValueModel(),rows)['updates'],0)

    def test_historical_comparisons_are_retained_without_cross_policy_pooling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = {'schema':'crawl-general-v1','actions':[{'kind':'WAIT'}]}
            for cycle in range(2):
                name = f'cycle-{cycle:04d}-counterfactual'
                (root / (name + '.result.json')).write_text('{"steps":1}')
                (root / (name + '.jsonl')).write_text(json.dumps({
                    'observation':state, 'action_index':0, 'return':10,
                    'policy_version':f'cycle-{cycle:04d}:counterfactual'})+'\n')
            rows = rows_from_replay(root)
            self.assertEqual(len(rows),2)
            self.assertNotEqual(rows[0]['comparison_id'],rows[1]['comparison_id'])


if __name__ == '__main__':
    unittest.main()
