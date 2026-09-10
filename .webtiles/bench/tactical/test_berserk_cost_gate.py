import unittest

from learn_berserk_cost_gate import OUTCOME_VALUE,utility


class BerserkCostGateTests(unittest.TestCase):
    def test_activation_cost_only_changes_recovery_ties(self):
        self.assertEqual(utility({'outcome':'recovered_quiet','activations':[]}),100)
        self.assertEqual(utility({'outcome':'recovered_quiet','activations':[{'turn':1}]}),98)
        self.assertEqual(utility({'outcome':'death','activations':[{'turn':1}]}),-102)
        self.assertEqual(utility({'outcome':'budget_truncated','activations':[]}),0)

    def test_outcome_scale_preserves_necessity(self):
        self.assertGreater(OUTCOME_VALUE['recovered_quiet']-2,OUTCOME_VALUE['death'])
        self.assertGreater(OUTCOME_VALUE['recovered_quiet']-2,OUTCOME_VALUE['budget_truncated'])


if __name__=='__main__':unittest.main()
