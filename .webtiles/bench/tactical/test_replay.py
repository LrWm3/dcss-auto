import copy
import unittest
import random
import tempfile
from pathlib import Path
from unittest.mock import patch
from train_encounters import guarded_actions
from train_encounters import run_episode
from train_replay import credit, credited, Replay
from test_training import state


class ReplayTests(unittest.TestCase):
    def test_hazards_delegate(self):
        for flag in ('on_fire','poisoned','confused'):
            self.assertEqual(guarded_actions(state(**{flag:True})),['baseline'])
        self.assertEqual(guarded_actions(state(monsters={})),['baseline'])
        self.assertEqual(guarded_actions(state(cells={'0:0':{'cloud':True}})),['baseline'])
        self.assertNotIn('wait',guarded_actions(state()))

    def test_credit_waits_for_audit(self):
        self.assertEqual(credit({'outcome':'safe_recovery'}),0)
        for end,expected in [('death',-1),('floor_change',1),('no_turn_stall',0),('budget_alive',0)]:
            self.assertEqual(credit({'outcome':'safe_recovery','handoff':{'outcome':end}}),expected)
        self.assertEqual(credit({'outcome':'safe_recovery','handoff':{
            'outcome':'budget_alive','recovered_at_end':True}}),1)

    def rows(self):
        return [dict(features={'bias':1},allowed=['baseline','wait'],action='baseline',
            next_features={'bias':1},next_allowed=['baseline','wait'],reward=0.,end=False)
            for _ in range(8)]

    def test_multistep_stops_at_endpoint_and_preserves_source(self):
        source=self.rows();rows=credited(source,{'outcome':'death'})
        self.assertEqual(rows[0]['n_reward'],0)
        self.assertEqual(rows[3]['n_reward'],-1)
        self.assertTrue(rows[3]['n_end'])
        self.assertFalse(source[-1]['end'])
        self.assertEqual(rows[-1]['reward'],-1)

    def test_target_is_frozen_until_sync_and_demos_permanent(self):
        demos=credited(self.rows(),{'outcome':'floor_change'})
        learner=Replay(demos);before=copy.deepcopy(learner.demos)
        learner.learn(1)
        self.assertNotEqual(learner.model,{})
        self.assertEqual(learner.target,{})
        learner.online.extend(credited(self.rows(),{'outcome':'death'}))
        learner.learn(24)
        self.assertEqual(learner.target,learner.model)
        self.assertEqual(learner.demos,before)
        learner.model['baseline']['bias']+=1
        self.assertNotEqual(learner.target,learner.model)

    def test_rollout_records_shield_and_delayed_death_without_learning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            class Fake:
                work=root
                calls=[]
                def reset(self,case): return state(on_fire=True)
                def step(self,action):
                    self.calls.append(action)
                    if len(self.calls)==1: return state(turn=11,monsters={},safe=True)
                    return {'terminal':'death'}
                def close(self): pass
            fake=Fake();rows=[];model={'wait':{'bias':10}}
            cfg=dict(steps=5,turns=100,alpha=.03,gamma=1,hazard_shield=True,handoff_steps=2)
            with patch('train_encounters.Environment',return_value=fake):
                r=run_episode(dict(id='x',seed='1',case='unused'),root,'q',model,
                    random.Random(1),cfg,selector=lambda s,m,a:a[0],transitions=rows)
            self.assertEqual(fake.calls,['baseline','baseline'])
            self.assertEqual(rows[0]['allowed'],['baseline'])
            self.assertEqual(credited(rows,r)[0]['reward'],-1)
            self.assertEqual(model,{'wait':{'bias':10}})


if __name__=='__main__': unittest.main()
