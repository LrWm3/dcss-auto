import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from general_env import GeneralEnvironment
from teacher import choose_action
from evaluate import promotion_decision
from train_model import train_behavioral_clone, train_q_finetune
from model import ActionValueModel, tensor_for_actions
import math
import torch


class FoundationTests(unittest.TestCase):
    def test_routes_around_wall(self):
        cells = {(0,0): {}, (0,1): {}, (0,2): {}, (1,2): {},
                 (2,2): {}, (2,1): {}, (2,0): {"frontier": True}}
        state = {"player": {"hp": 10, "max_hp": 10}, "monsters": [],
                 "known": {f"{x}:{y}": dict(x=x,y=y,traversable=True,**c)
                           for (x,y),c in cells.items()},
                 "actions": [{"kind":"WAIT"}, {"kind":"MOVE","dx":0,"dy":1}]}
        self.assertEqual(choose_action(state), 1)

    def test_stairs(self):
        state = {"player":{"hp":10,"max_hp":10}, "actions":[
            {"kind":"WAIT"}, {"kind":"TAKE_STAIRS_DOWN"}]}
        self.assertEqual(choose_action(state), 1)

    def test_score_format(self):
        self.assertEqual(GeneralEnvironment._parse_score(
            "Game seed: 1\n\n49 CodexGeneral the Chopper (level 3, -13/33 HPs)\n"),49)

    def test_no_promotion_on_truncation(self):
        a = {"results":[{"seed":str(i),"terminal":False,"score":None} for i in range(5)]}
        self.assertFalse(promotion_decision(a,a)["promote"])

    def test_score_promotion(self):
        a = {"results":[{"seed":str(i),"terminal":True,"score":10} for i in range(10)]}
        b = {"results":[{"seed":str(i),"terminal":True,"score":20} for i in range(10)]}
        self.assertTrue(promotion_decision(a,b)["promote"])
        self.assertFalse(promotion_decision(b,a)["promote"])

    def test_unlabelled_actor_not_cloned_and_missing_return_not_zero(self):
        m = ActionValueModel()
        before = {k:v.clone() for k,v in m.state_dict().items()}
        row = {"policy_version":"actor", "observation":{"schema":"crawl-general-v1",
            "actions":[{"kind":"WAIT"}]}, "action_index":0, "return":None}
        _, metadata = train_behavioral_clone([row],model=m)
        self.assertEqual(metadata["usable"],0)
        self.assertEqual(train_q_finetune(m,[row])["usable"],0)
        self.assertTrue(all(torch.equal(v,m.state_dict()[k]) for k,v in before.items()))

    def test_real_score_target_updates_parameters_toward_return(self):
        torch.manual_seed(7)
        model = ActionValueModel()
        state = {"schema":"crawl-general-v1", "actions":[{"kind":"WAIT"}]}
        features = tensor_for_actions(state,state["actions"])
        target = math.log1p(49)
        initial = abs(model(features).item()-target)
        result = train_q_finetune(model,[{"observation":state,
            "action_index":0,"return":49}],epochs=5)
        self.assertEqual(result["usable"],5)
        self.assertLess(abs(model(features).item()-target),initial)


if __name__ == '__main__':
    unittest.main()
