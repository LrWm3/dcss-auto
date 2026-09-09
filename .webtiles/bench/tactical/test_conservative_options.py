import copy
import math
import json
from pathlib import Path
import unittest
from conservative_options import select_option, ConservativeController
from test_training import state, MEM
from train_encounters import guarded_actions


class ConservativeTests(unittest.TestCase):
    def test_near_tie_prefers_best_alternative_not_always_retreat(self):
        model={'rage_hold':{'bias':.70},'retreat':{'bias':.69},'hold':{'bias':.2}}
        self.assertEqual(select_option(model,{'bias':1})['option'],'retreat')
        model['baseline']={'bias':.695}
        self.assertEqual(select_option(model,{'bias':1})['option'],'baseline')

    def test_clear_advantage_preserves_rage(self):
        model={'rage_hold':{'bias':1.1266},'baseline':{'bias':.9939}}
        self.assertEqual(select_option(model,{'bias':1})['option'],'rage_hold')

    def test_other_choices_unchanged_and_no_score_mutation(self):
        model={'hold':{'bias':1}};before=copy.deepcopy(model)
        self.assertEqual(select_option(model,{'bias':1})['option'],'hold')
        self.assertEqual(model,before)
        self.assertEqual(select_option({}, {'bias':1})['option'],'retreat')

    def test_rejects_bad_margin_and_scores(self):
        for m in [-1,math.inf,math.nan]:
            with self.assertRaises(ValueError):select_option({}, {'bias':1},m)
        with self.assertRaises(ValueError):select_option({'hold':{'bias':math.nan}}, {'bias':1})

    def test_persistent_option_and_hazard_override(self):
        model={'rage_hold':{'bias':.7},'hold':{'bias':.69}}
        c=ConservativeController(model);s=state()
        c(s,MEM,guarded_actions(s));t=c.tactic
        self.assertEqual(c.option,'hold')
        s=state(poisoned=True)
        self.assertEqual(c(s,MEM,guarded_actions(s)),'baseline')
        self.assertIs(t,c.tactic)

    def test_recorded_training_regressions(self):
        root=Path(__file__).parent/'artifacts/options-expanded-v1'
        if not (root/'model.json').exists():self.skipTest('Local experiment artifacts unavailable')
        model=json.loads((root/'model.json').read_text())
        rows=json.loads((root/'training-outcomes.json').read_text())
        lookup={(r['case_id'],r['option']):r for r in rows}
        expected={
            'mining-deeper-v1/collection/encounter-005':'retreat',
            'mining-option-training-v1/collection/encounter-002':'rage_hold',
            'mining-option-training-v1/collection/encounter-005':'baseline'}
        for case,option in expected.items():
            chosen=select_option(model,lookup[case,'retreat']['features'])['option']
            self.assertEqual(chosen,option)
            self.assertEqual(lookup[case,chosen]['credit'],1)


if __name__=='__main__':unittest.main()
