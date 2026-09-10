import unittest
from unittest.mock import patch
import numpy as np
import torch
from direction_policy import directional_features, cap_probabilities, DirectionPolicy, WIDTH
from action_env import ACTIONS
from experiment import DIRECTIONS


class DirectionTests(unittest.TestCase):
    def test_caps_rare_examples_without_losing_normalization(self):
        p=np.array([.2]+[.8/999]*999)
        q=cap_probabilities(p)
        self.assertAlmostEqual(q.sum(),1)
        self.assertLessEqual(q.max(),.004+1e-12)
        self.assertTrue((q>0).all())
        np.testing.assert_allclose(cap_probabilities(p,1),np.full(1000,.001))

    def test_invalid_probabilities_rejected(self):
        for p in ([],[0,1],[float('nan'),1],[-1,2]):
            with self.assertRaises(ValueError):cap_probabilities(p)

    def test_enemy_and_route_features_are_direction_specific(self):
        s=dict(hp=10,max_hp=20,known={str(i):dict(x=x,y=y,traversable=True,feature='floor')
            for i,(x,y) in enumerate(DIRECTIONS.values())},monsters={'a':dict(x=1,y=0,threat=2)})
        with patch('direction_policy.paths',return_value={(1,0):['e']}):
            f=directional_features(s,np.ones(10,dtype=bool))
            changed=directional_features({**s,'seed':'irrelevant','turn':100,'outcome':'irrelevant'},np.ones(10,dtype=bool))
        self.assertEqual(f.shape,(10,WIDTH));np.testing.assert_array_equal(f,changed)
        east=ACTIONS.index('e');west=ACTIONS.index('w')
        self.assertEqual(f[east,22],1);self.assertEqual(f[west,22],0)
        self.assertEqual(f[east,27],1);self.assertEqual(f[west,27],0)

    def test_shared_scorer_and_mask(self):
        model=DirectionPolicy();x=torch.zeros(10,WIDTH);mask=torch.ones(10,dtype=torch.bool)
        with torch.no_grad():
            scores=model(x,mask)
            self.assertTrue(torch.allclose(scores,scores[0].expand(10)))
            mask[0]=False
            self.assertEqual(model(x,mask)[0].item(),-1e9)


if __name__=='__main__':unittest.main()
