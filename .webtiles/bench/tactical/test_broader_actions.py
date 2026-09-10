import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from action_env import ACTIONS
from broaden_action_training import combat_metrics


class CombatMetricTests(unittest.TestCase):
    def test_counts_visible_adjacency_and_teacher_disagreement_separately(self):
        states=[{'monsters':{'a':{'x':1,'y':0}}},
                {'monsters':[{'x':3,'y':0}]}, {'monsters':{}}, {'terminal':'death'}]
        events=[{'initial_observation':states[0]}]+[{'next_observation':s} for s in states[1:]]
        actions=[{'action':'wait','mask':[True]*10} for _ in range(3)]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'events.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in events))
            (root/'actions.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in actions))
            with patch('broaden_action_training.fixed_action',side_effect=[0,0,ACTIONS.index('wait')]):
                result=combat_metrics({'worker':tmp})
        self.assertEqual(result,dict(decisions=3,adjacent_enemy_decisions=1,
                                    adjacent_enemy_waits=1,wait_when_teacher_would_act=2))


if __name__=='__main__':unittest.main()
