import copy
import json
from pathlib import Path
import random
import tempfile
import unittest
import torch

from archive_sampling import select_cases
from counterfactual import empirical_return
from features import state_features, action_features, STATE_DIM, ACTION_DIM
from model import ActionValueModel, load_model, tensor_for_actions
from policy import Policy
from train_model import train_return_policy


class ScorePolicyTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        torch.manual_seed(4)
        self.state = {'schema':'crawl-general-v1', 'player':{},
                      'actions':[{'kind':'WAIT'}, {'kind':'MOVE','dx':1,'dy':0}],
                      'monsters':[{'x':1,'y':0,'damage_level':0}],
                      'inventory':[{'slot':0,'class':'weapon','equipped':True,'damage':10}]}

    def test_new_features_change_with_combat_properties(self):
        original = state_features(self.state)
        self.assertEqual(len(original), STATE_DIM)
        for field in ('res_fire','res_poison','willpower','poisoned','on_fire'):
            changed = copy.deepcopy(self.state)
            changed['player'][field] = 1
            self.assertNotEqual(state_features(changed), original, field)
        for group, field in [('monsters','damage_level'),('inventory','damage')]:
            changed = copy.deepcopy(self.state)
            changed[group][0][field] = 5
            self.assertNotEqual(state_features(changed), original)
        action = {'kind':'MELEE','x':1,'y':0}
        self.assertEqual(len(action_features(self.state, action)), ACTION_DIM)
        changed = copy.deepcopy(self.state)
        changed['monsters'][0]['damage_level'] = 5
        self.assertNotEqual(action_features(changed,action), action_features(self.state,action))

    def test_tactical_geometry_and_hazards_reach_the_encoder(self):
        state = copy.deepcopy(self.state)
        state['known'] = {'1:0': {'x': 1, 'y': 0, 'frontier': True,
                                  'traversable': True, 'unsafe': False}}
        state['cells'] = {'1:0': {'x': 1, 'y': 0, 'cloud': 'steam',
                                  'invisible_monster': True}}
        state['monsters'][0].update({'reachable': False, 'range': 6,
                                     'is_unique': True})
        baseline = state_features(state)
        changed = copy.deepcopy(state)
        changed['known']['1:0']['unsafe'] = True
        changed['cells']['1:0']['cloud'] = 'liquid fire'
        changed['monsters'][0]['reachable'] = True
        self.assertNotEqual(state_features(changed), baseline)
        self.assertNotEqual(action_features(state, {'kind': 'MOVE', 'dx': 1, 'dy': 0}),
                             action_features(changed, {'kind': 'MOVE', 'dx': 1, 'dy': 0}))

    def test_official_cutoffs_count_but_errors_do_not(self):
        outcomes = [{'score_status':'final_official','score':10},
                    {'score_status':'cutoff_official','score':20}]
        self.assertEqual(empirical_return(outcomes,2),15)
        self.assertIsNone(empirical_return(outcomes[:1]+[{'error':'timeout'}],2))
        self.assertIsNone(empirical_return([{'score_status':'unavailable','score':-1}],1))

    def test_legacy_migration_preserves_logits_and_values(self):
        model = ActionValueModel()
        weights = model.state_dict()
        for key in ('net.0.weight','value_net.0.weight'):
            weights[key] = torch.cat((weights[key][:,:192],weights[key][:,STATE_DIM:STATE_DIM+96]),1)
        x = tensor_for_actions(self.state, self.state['actions'])
        old_x = torch.cat((x[:,:192], x[:,STATE_DIM:STATE_DIM+96]),1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'old.pt'
            torch.save({'model_version':'general-action-model-v2-separate-critic',
                        'feature_version':'general-features-v4-route-deltas',
                        'state_dict':weights, 'hidden':192},path)
            migrated, payload = load_model(path)
            for name in ('net','value_net'):
                old = copy.deepcopy(getattr(model,name))
                old[0] = torch.nn.Linear(288,192)
                old.load_state_dict({k[len(name)+1:]:v for k,v in weights.items() if k.startswith(name+'.')})
                torch.testing.assert_close(getattr(migrated,name)(x),old(old_x))
            self.assertIn('feature_migration',payload['metadata'])

    def test_returns_change_policy_without_following_teacher(self):
        base = ActionValueModel()
        # Known baseline log-score 1, so zero return is negative and 100 positive.
        for parameter in base.value_net.parameters():
            parameter.data.zero_()
        base.value_net[-1].bias.data.fill_(1)
        x = tensor_for_actions(self.state,self.state['actions'])
        initial = base(x).softmax(-1)[0].item()
        for score, direction in [(100,1),(0,-1)]:
            model = copy.deepcopy(base)
            result = train_return_policy(model,[{'observation':self.state,'action_index':0,
                'teacher_action_index':1, 'behavior_probability':0.5,'return':score}])
            self.assertGreater(result['updates'],0)
            self.assertGreater((model(x).softmax(-1)[0].item()-initial)*direction,0)
            kl = torch.nn.functional.kl_div(model(x).log_softmax(-1),base(x).softmax(-1),reduction='sum')
            self.assertLessEqual(float(kl.detach()),.01+1e-6)

    def test_missing_behavior_is_not_assumed_on_policy(self):
        result = train_return_policy(ActionValueModel(),[{'observation':self.state,
                    'action_index':0,'return':100}])
        self.assertEqual(result['updates'],0)

    def test_old_frozen_run_requires_successor(self):
        from train_crawl_agent import prepare
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'learner').mkdir()
            (root/'learner'/'cycle-0000.ready.json').write_text('{}')
            (root/'config.json').write_text(json.dumps({'feature_version':'general-features-v4-route-deltas'}))
            with self.assertRaisesRegex(ValueError,'prepare_successor'):
                prepare(root,object())

    def test_epsilon_probability_is_exact(self):
        policy = Policy(ActionValueModel(),epsilon=.2,rng=random.Random(5))
        greedy = int(policy.model(tensor_for_actions(self.state,self.state['actions'])).argmax())
        for _ in range(20):
            i,_ = policy.choose(self.state)
            self.assertAlmostEqual(policy.last_action_probability, .9 if i==greedy else .1)

    def test_archive_covers_early_and_danger_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=[]
            for i,category in enumerate(['encounter_start','healthy','danger','coverage']*3):
                folder=Path(tmp)/str(i); folder.mkdir()
                (folder/'sampling.json').write_text(json.dumps({'category':category}))
                paths.append(folder/'case.json')
            selected=select_cases(paths,1)
            self.assertEqual(len(selected),4)
            self.assertEqual({json.loads((p/'sampling.json').read_text())['category'] for p in selected},
                             {'encounter_start','healthy','danger','coverage'})
            self.assertEqual(selected,select_cases(paths,1))


if __name__ == '__main__':
    unittest.main()
