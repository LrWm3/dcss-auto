import copy
import tempfile
import unittest
import sys
import os
from unittest.mock import patch, MagicMock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import torch
from episode_budget import DecisionBudget
from model import ActionValueModel, tensor_for_actions, save_model, load_model
from train_model import train_q_finetune, train_counterfactual_preferences


class BudgetTests(unittest.TestCase):
    def test_new_floor_has_own_budget_and_revisits_do_not_reset(self):
        b = DecisionBudget(2)
        one = {"level":"D:1","turn":1}
        two = {"level":"D:2","turn":2}
        b.record(one, one); b.record(one, two)
        self.assertIsNone(b.reason(two))
        b.record(two, one)
        self.assertEqual(b.reason(one), "floor_decision_limit")
        self.assertEqual(b.summary()["decisions_by_floor"], {"D:1":2,"D:2":1})

    def test_branch_floors_distinct_and_global_limit(self):
        b = DecisionBudget(2,total=2)
        d, lair = {"level":"D:1","turn":1}, {"level":"Lair:1","turn":2}
        b.record(d,lair)
        self.assertIsNone(b.reason(lair))
        b.record(lair,d)
        self.assertEqual(b.reason(d),"total_decision_limit")

    def test_no_turn_and_real_death(self):
        b = DecisionBudget(2000,no_turn=2)
        state={"level":"D:1","turn":0}
        b.record(state,state); b.record(state,state)
        self.assertEqual(b.reason(state),"no_game_time_progress")
        self.assertIsNone(b.reason({**state,"terminal":"death"}))

    def test_collector_can_exceed_one_floor_allowance_and_saves_cutoff(self):
        from collect import run_episode
        def state(level, turn):
            return {"schema":"crawl-general-v1","level":level,"turn":turn,
                    "actions":[{"kind":"WAIT"}],"player":{"hp":10,"max_hp":10},
                    "terminal":False}
        env=MagicMock()
        env.launch.return_value=state("D:1",0)
        env.step.side_effect=[state("D:1",1),state("D:2",2),state("D:2",3),state("D:2",4)]
        env.works=[]
        with tempfile.TemporaryDirectory() as directory:
            env.work_path=Path(directory)
            with patch("collect.GeneralEnvironment",return_value=env):
                result=run_episode(directory,"1",2,snapshot=False,total_steps=10)
        self.assertEqual(result["steps"],4)
        self.assertEqual(result["decision_budget"]["decisions_by_floor"],{"D:1":2,"D:2":2})
        self.assertEqual(result["truncation_reason"],"floor_decision_limit")
        self.assertFalse(result["terminal"])
        self.assertIsNone(result["score"])
        self.assertTrue(result["resume_checkpoint"])
        env.save_state.assert_called_once()

    def test_return_training_cannot_change_any_actor_parameters(self):
        torch.manual_seed(2)
        m=ActionValueModel()
        before=copy.deepcopy(m.net.state_dict())
        state={"schema":"crawl-general-v1","actions":[{"kind":"WAIT"},{"kind":"MOVE","dx":1}]}
        train_q_finetune(m,[{"observation":state,"action_index":0,"return":50}],epochs=3)
        self.assertTrue(all(torch.equal(v,m.net.state_dict()[k]) for k,v in before.items()))

    def test_paired_preferences_move_ordering_and_ignore_missing(self):
        torch.manual_seed(2)
        m=ActionValueModel()
        state={"schema":"crawl-general-v1","actions":[{"kind":"WAIT"},{"kind":"MOVE","dx":1}]}
        rows=[{"observation":state,"action_index":0,"return":None},
              {"observation":state,"action_index":1,"return":50}]
        self.assertEqual(train_counterfactual_preferences(m,rows)["updates"],0)
        rows[0]["return"]=1
        result=train_counterfactual_preferences(m,rows)
        self.assertGreater(result["margins_after"][0],result["margins_before"][0])

    def test_old_checkpoint_migration_preserves_policy_exactly(self):
        from features import FEATURE_VERSION
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"old.pt"
            m=ActionValueModel()
            torch.save({"model_version":"general-action-model-v1","feature_version":FEATURE_VERSION,
                "hidden":192,"state_dict":{"net."+k:v for k,v in m.net.state_dict().items()}},p)
            migrated,_=load_model(p)
            self.assertTrue(all(torch.equal(v,migrated.net.state_dict()[k]) for k,v in m.net.state_dict().items()))

    @unittest.skipUnless(os.environ.get("CRAWL_STORAGE_LIVE_TEST"), "opt-in real engine test")
    def test_rejected_action_mask_survives_real_save_restore(self):
        import general_env
        real_make_rc=general_env.make_rc
        def test_rc(path, source_rc=None):
            real_make_rc(path,source_rc)
            source=path.read_text()
            at=source.rfind(">")
            # Seed an adapter rejection only in the original process (seq 1).
            # Restored processes start at seq 0, so must use the saved mask.
            hook='''
local test_ready = ready
function ready()
  if GA.seq == 1 and you.turns() == 1 then
    GA.rejected_turn = 1
    GA.rejected_actions = {["WAIT|||||||"]=true}
  end
  test_ready()
end
'''
            path.write_text(source[:at]+hook+source[at:])
            return path
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            left=general_env.GeneralEnvironment(root/"left")
            right=general_env.GeneralEnvironment(root/"right")
            try:
                with patch("general_env.make_rc",side_effect=test_rc):
                    initial=left.launch()
                index=next(i for i,a in enumerate(initial["actions"]) if a["kind"]=="WAIT")
                after=left.step(index)
                self.assertFalse(any(a["kind"]=="WAIT" for a in after["actions"]))
                left.save_state(root/"case")
                restored=right.launch(root/"case")
                self.assertEqual(after["actions"],restored["actions"])
            finally:
                left.close(); right.close()


if __name__=="__main__":
    torch.set_num_threads(1)
    unittest.main()
