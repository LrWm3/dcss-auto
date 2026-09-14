import train_ppo_pilot  # Set the pilot's explicit, versioned environment modes.
import copy
import math
import random
import unittest
from unittest.mock import patch
import torch
from ppo_core import reward_delta,advantages,policy_loss,sample,fit_ppo
from structured_model import StructuredScorer
import structured_features as features


class PPOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):torch.set_num_threads(1)

    def test_score_telescopes_including_death(self):
        states=[{'score':s} for s in [10,15,18,12]]
        self.assertAlmostEqual(sum(reward_delta(a,b) for a,b in zip(states,states[1:])),.002)
        with self.assertRaises(ValueError):reward_delta({'score':None},{'score':2})
        with self.assertRaises(ValueError):reward_delta({'score':1},{'score':2,'score_version':'other'})

    def test_terminal_vs_rollout_boundary(self):
        rows=[dict(reward=1,value=2,next_value=7,terminated=False,segment_end=True),
              dict(reward=3,value=4,next_value=999,terminated=True,segment_end=True)]
        adv,returns=advantages(rows,1.)
        self.assertEqual(adv,[6,-1])
        self.assertEqual(returns,[8,3])

    def test_gae_does_not_cross_episodes(self):
        rows=[dict(reward=1,value=0,next_value=0,terminated=False,segment_end=False),
              dict(reward=2,value=0,next_value=0,terminated=True,segment_end=True),
              dict(reward=100,value=0,next_value=5,terminated=False,segment_end=True)]
        self.assertEqual(advantages(rows,1.)[0],[3,2,105])

    def test_clipped_policy_loss(self):
        loss=policy_loss(torch.tensor([math.log(2.)]),torch.tensor([0.]),torch.tensor([1.]))
        self.assertAlmostEqual(float(loss),-1.1,places=5)
        loss=policy_loss(torch.tensor([math.log(.5)]),torch.tensor([0.]),torch.tensor([-1.]))
        self.assertAlmostEqual(float(loss),.9,places=5)

    def test_sampling_is_seeded_and_not_greedy(self):
        p=torch.tensor([.2,.8]).log()
        a,b=random.Random(3),random.Random(3)
        aa=[sample(p,a) for _ in range(100)]
        self.assertEqual(aa,[sample(p,b) for _ in range(100)])
        self.assertEqual(set(aa),{0,1})

    def test_packed_logits_match_individual_and_gradients(self):
        model=StructuredScorer(16)
        s=torch.zeros(2,features.STATE_DIM)
        s[1,:features.GLOBAL_DIM]=.2
        a=torch.randn(5,features.ACTION_DIM)
        owners=torch.tensor([0,0,1,1,1])
        packed=model.packed(s,a,owners)
        individual=torch.cat([model((s[:1],a[:2])).squeeze(-1),model((s[1:],a[2:])).squeeze(-1)])
        torch.testing.assert_close(packed,individual,atol=1e-6,rtol=1e-5)
        packed.sum().backward()
        self.assertTrue(any(p.grad is not None for p in model.parameters()))

    def test_visible_bush_not_encoded_as_missing_target(self):
        state={'schema':'crawl-general-v1','actions':[]}
        a={'kind':'MELEE','dx':1,'dy':0,'x':1,'y':0}
        missing=features.action_features(state,a,[{},{}])
        visible=features.action_features(state,dict(a,target={'x':1,'y':0,'name':'bush','max_hp':50}),[{},{}])
        self.assertNotEqual(missing,visible)
        self.assertEqual(len(missing),len(visible))

    def test_real_update_and_rollback(self):
        class Scorer(torch.nn.Module):
            def __init__(self):
                super().__init__();self.layer=torch.nn.Linear(4,1)
            def packed(self,s,a,o):return self.layer(torch.cat([s[o],a],1)).squeeze(-1)
        class Tiny(torch.nn.Module):
            def __init__(self):
                super().__init__();self.net=Scorer();self.value_net=Scorer()
        model=Tiny()
        x=(torch.tensor([[.1,.2]]),torch.eye(2))
        old=model.net.packed(*x,torch.tensor([0,0])).log_softmax(0).detach().tolist()
        rows=[dict(observation={'actions':[{},{}]},action_index=i%2,log_probs=old,
                   value=0.,next_value=0.,reward=float(i%2),terminated=True,segment_end=True) for i in range(32)]
        actor=torch.optim.Adam(model.net.parameters(),lr=1e-4)
        critic=torch.optim.Adam(model.value_net.parameters(),lr=1e-4)
        saved=copy.deepcopy(model.state_dict())
        with patch('ppo_core.tensor_for_actions',return_value=x):
            result=fit_ppo(model,rows,actor,critic,7,epochs=1)
        self.assertTrue(result['updated'])
        self.assertTrue(any(not torch.equal(v,saved[k]) for k,v in model.state_dict().items()))
        # An excessive proposed update must restore BOTH model and optimizer.
        model.load_state_dict(saved)
        actor=torch.optim.SGD(model.net.parameters(),lr=1000.)
        critic=torch.optim.SGD(model.value_net.parameters(),lr=1000.)
        with patch('ppo_core.tensor_for_actions',return_value=x):
            result=fit_ppo(model,rows,actor,critic,7,epochs=1)
        self.assertFalse(result['updated'])
        for k,v in model.state_dict().items():torch.testing.assert_close(v,saved[k],rtol=0,atol=0)


if __name__=='__main__':unittest.main()
