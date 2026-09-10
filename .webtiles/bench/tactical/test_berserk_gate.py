import unittest
import numpy as np

from learn_berserk_gate import FEATURES,gate_context,select


class BerserkGateTests(unittest.TestCase):
    def test_context_is_observable_and_fixed_width(self):
        state=dict(hp=50,max_hp=100,can_berserk=True,monsters={},enemy_details={},
                   player={'xl':5,'ac':10,'ev':8})
        values=gate_context(state)
        self.assertEqual(len(values),len(FEATURES))
        self.assertEqual(values,gate_context(dict(state,seed='hidden',turn=99,outcome='death')))

    def test_gate_keeps_near_on_tie_and_requires_margin(self):
        state=dict(hp=50,max_hp=100,can_berserk=True,monsters={},enemy_details={},
                   player={'xl':5,'ac':10,'ev':8})
        self.assertEqual(select({'value':[.7,.7]},state),'near')
        self.assertEqual(select({'value':[.9,.8]},state),'never')
        self.assertEqual(select({'value':[.8,.86]},state),'near')


if __name__=='__main__':unittest.main()
