import unittest
import numpy as np
from action_env import ACTIONS
from train_action_dagger import stratum, sample_weights


class DaggerTests(unittest.TestCase):
    def test_groups_distinguish_threatened_wait(self):
        wait = ACTIONS.index('wait')
        self.assertEqual(stratum({},0),0)
        self.assertEqual(stratum({'monsters':{'1':{}}},wait),1)
        self.assertEqual(stratum({'unseen':True},wait),1)
        self.assertEqual(stratum({},wait),2)

    def test_group_mass_and_mistake_priority(self):
        groups = np.array([0,0,1,2,2,2])
        weights = sample_weights(groups,np.array([False,True,False,False,False,False]))
        np.testing.assert_allclose([weights[groups==g].sum() for g in range(3)],[.6,.2,.2])
        self.assertAlmostEqual(weights[1],2*weights[0])

    def test_absent_group_renormalizes(self):
        np.testing.assert_allclose(sample_weights(np.array([0,2]),np.array([False,False])),[.75,.25])
        with self.assertRaises(ValueError):
            sample_weights(np.array([],dtype=int),np.array([],dtype=bool))


if __name__=='__main__': unittest.main()
