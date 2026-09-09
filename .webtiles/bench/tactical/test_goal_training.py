import unittest
from goal_controllers import available
from run_goals import fit,select,options,normalized
from test_goal_controllers import state

class GoalTrainingTest(unittest.TestCase):
    def test_monster_order_not_identity(self):
        a=dict(name='gnoll',x=1,y=0);b=dict(name='gnoll',x=2,y=1)
        self.assertEqual(normalized({'monsters':{'1':a,'2':b}}),
                         normalized({'monsters':{'1':b,'2':a}}))
        self.assertNotEqual(normalized({'monsters':{'1':a}}),
                            normalized({'monsters':{'1':b}}))
    def test_validation_never_fit(self):
        with self.assertRaises(ValueError): fit([dict(split='validation')])
        with self.assertRaises(ValueError): fit([dict(split='test')])
    def test_masked_goals_never_selected(self):
        s=state();s['anchors']={}
        self.assertNotIn('withdraw',available(s))
        self.assertNotEqual(select({'withdraw:1':{'bias':100}},s),'withdraw:1')
    def test_joint_choice_supports_independent_rage(self):
        s=state()
        for g in available(s):
            self.assertIn(g+':0',options(s));self.assertIn(g+':1',options(s))
            for b in (0,1):
                o=g+':'+str(b)
                self.assertEqual(select({o:{'bias':10}},s),o)
    def test_fit_outcomes_not_old_proxy(self):
        rows=[dict(split='train',outcome='recovered_quiet',credit=1.,
              features={'bias':1.},option='defend:0'),
              dict(split='train',outcome='death',credit=-1.,
              features={'bias':1.},option='pursue:1')]
        model=fit(rows,100)
        self.assertGreater(model['defend:0']['bias'],.9)
        self.assertLess(model['pursue:1']['bias'],-.9)

if __name__=='__main__': unittest.main()
