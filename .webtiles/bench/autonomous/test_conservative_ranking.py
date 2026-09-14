import unittest
from unittest.mock import patch
import torch
from conservative_ranking import bounded_fit
from conservative_ranking import credible_pair, ranking_groups, within_budget
from retry_exploration_fit import loop_tick, screen_gate


def row(index, scores):
    return {'action_index': index, 'empirical_return': sum(scores)/len(scores),
            'observation': {}, 'outcomes': [
                {'score': s, 'score_status': 'cutoff_official'} for s in scores]}


class ConservativeTests(unittest.TestCase):
    def test_rejected_epoch_restores_parameters(self):
        class Tiny(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.net = torch.nn.Linear(2,1)
            def forward(self,x):
                return self.net(x).squeeze(-1)
        model = Tiny()
        original = {k:v.clone() for k,v in model.state_dict().items()}
        groups = [[row(0,[20]*3),row(1,[10]*3)]]
        with patch('conservative_ranking.tensor_for_actions', return_value=torch.eye(2)), \
             patch('conservative_ranking._actions', return_value=[{},{}]), \
             patch('conservative_ranking.within_budget', return_value=False):
            report = bounded_fit(model, groups, [{}], epochs=1)
        self.assertFalse(report['trained'])
        for k,v in model.state_dict().items():
            torch.testing.assert_close(v,original[k],rtol=0,atol=0)

    def test_noise_not_a_preference(self):
        self.assertFalse(credible_pair(row(0, [88,132,37]), row(1, [87,79,88])))
        self.assertFalse(credible_pair(row(0, [33,33,46]), row(1, [33,33,33])))

    def test_consistent_advantage(self):
        a, b = row(0, [20,30,40]), row(1, [10,20,30])
        self.assertTrue(credible_pair(a,b))
        self.assertFalse(credible_pair(b,a))
        self.assertEqual(ranking_groups([[a,b]])[0][1], [(0,1)])

    def test_tiny_advantages_ignored(self):
        self.assertFalse(credible_pair(row(0,[100.1]*3), row(1,[100]*3)))

    def test_invalid_and_mixed_objectives(self):
        a,b=row(0,[20]*3),row(1,[10]*3)
        a['outcomes'][0]['error']='crash'
        self.assertFalse(credible_pair(a,b))
        a=row(0,[20]*3)
        a['outcomes'][0]['score_version']='different'
        self.assertFalse(credible_pair(a,b))
        self.assertFalse(credible_pair(row(0,[20]*2),row(1,[10]*2)))

    def test_bounds(self):
        self.assertTrue(within_budget(dict(mean_kl=.01,max_kl=.1,changed_fraction=.04)))
        for key, value in [('mean_kl',.03),('max_kl',.2),('changed_fraction',.06)]:
            audit=dict(mean_kl=.01,max_kl=.1,changed_fraction=.04)
            audit[key]=value
            self.assertFalse(within_budget(audit))

    def test_equipment_and_movement_loops(self):
        state={'visit_memory': {'since_discovery':30,'since_new_tile':30}}
        for kinds in [('REMOVE','WEAR'), ('MOVE','MOVE')]:
            actions=[{'kind':kinds[0],'dx':1},{'kind':kinds[1],'dx':-1}]*2
            self.assertTrue(loop_tick(state,actions))
        self.assertFalse(loop_tick(state,[{'kind':'MELEE'}]*4))

    def test_screen_rejects_regression(self):
        old=dict(case='a',steps=256,loop_ticks=0,equipment_actions=0,score=20,training_score=300)
        self.assertTrue(screen_gate([old],[dict(old)])['passed'])
        for changes in [dict(loop_ticks=30),dict(equipment_actions=100),dict(score=1),dict(error='crash')]:
            self.assertFalse(screen_gate([old],[dict(old,**changes)])['passed'])


if __name__ == '__main__':
    unittest.main()
