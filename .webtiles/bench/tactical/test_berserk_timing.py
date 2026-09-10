import unittest
import numpy as np
from learn_berserk_timing import trigger,fit_tree,predict,choose,context


class BerserkTimingTests(unittest.TestCase):
    def test_timing_and_availability(self):
        s=dict(hp=80,max_hp=100,monsters={'a':dict(x=2,y=0,threat=2)})
        mask=np.ones(10,dtype=bool)
        self.assertTrue(trigger('near',s,mask,False))
        self.assertFalse(trigger('contact',s,mask,False))
        s['monsters']['a']['x']=1
        self.assertTrue(trigger('contact',s,mask,False))
        self.assertFalse(trigger('late',s,mask,False))
        s['hp']=70
        self.assertTrue(trigger('late',s,mask,False))
        self.assertFalse(trigger('late',s,mask,True))
        mask[-1]=False
        self.assertFalse(trigger('near',s,mask,False))
        self.assertFalse(trigger('never',s,np.ones(10,dtype=bool),False))

    def test_tree_generalizes_leaf_means(self):
        x=np.arange(6)[:,None];y=np.array([[1,0,0,0]]*3+[[0,1,0,0]]*3)
        tree=fit_tree(x,y)
        self.assertEqual(choose(tree,[0]),'never')
        self.assertEqual(choose(tree,[5]),'contact')
        self.assertEqual(tree['left']['families'],3)
        self.assertEqual(tree['right']['families'],3)

    def test_advantage_gate_and_ties(self):
        self.assertEqual(choose({'value':[.8,.89,.85,.8]},[]),'never')
        self.assertEqual(choose({'value':[.8,.9,.9,.8]},[]),'contact')
        self.assertEqual(choose({'value':[1,1,1,1]},[]),'never')

    def test_context_excludes_identity_seed_and_outcome(self):
        s=dict(hp=50,max_hp=100,monsters={},can_berserk=True)
        self.assertEqual(context(s),context(dict(s,seed='123',turn=100,outcome='death')))


if __name__=='__main__':unittest.main()
