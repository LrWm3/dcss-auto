import copy
import unittest
from train_options import OptionController, OPTIONS, fit
from train_encounters import guarded_actions, value
from test_training import state, MEM


class OptionsTests(unittest.TestCase):
    def test_option_persists_and_eval_weights_frozen(self):
        model={'hold':{'hp':2},'retreat':{'bias':1}}
        before=copy.deepcopy(model);c=OptionController(model)
        s=state();c(s,MEM,guarded_actions(s))
        self.assertEqual(c.option,'hold');tactic=c.tactic
        s=state(hp=10);c(s,MEM,guarded_actions(s))
        self.assertEqual(c.option,'hold');self.assertIs(c.tactic,tactic)
        self.assertEqual(model,before)

    def test_shield_overrides_without_reselecting(self):
        c=OptionController(fixed='retreat');s=state(cells={'0:0':{'cloud':True}})
        self.assertEqual(c(s,MEM,guarded_actions(s)),'baseline')
        self.assertEqual(c.option,'retreat');self.assertEqual(c.overrides,1)

    def test_fixed_controller_matches_tactic_with_shield(self):
        from tactical_options import Tactic
        for option in OPTIONS:
            c=OptionController(fixed=option);t=Tactic(option)
            for s in [state(),state(poisoned=True),state(monsters={},safe=True)]:
                allowed=guarded_actions(s);expected=t(s)
                self.assertEqual(c(s,MEM,allowed),expected if expected in allowed else 'baseline')

    def test_fit_uses_outcomes_not_case_identity(self):
        rows=[dict(features={'bias':1},option=a,credit=1 if a=='hold' else -1,
                   case_id='secret',seed='hidden') for a in OPTIONS]
        before=copy.deepcopy(rows);model=fit(rows,100)
        self.assertEqual(max(OPTIONS,key=lambda a:value(model,a,{'bias':1})),'hold')
        self.assertNotIn('secret',str(model));self.assertEqual(rows,before)
        self.assertGreater(value(model,'hold',{'bias':1}),.99)

    def test_bad_options_rejected(self):
        with self.assertRaises(ValueError): OptionController(fixed='invalid')
        with self.assertRaises(ValueError): fit([])


if __name__=='__main__': unittest.main()
