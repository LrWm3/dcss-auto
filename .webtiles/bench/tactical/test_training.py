import copy
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from bench import sha
from train_encounters import actions,features,choose,update,outcome,reward_for,load_cases,run_episode


def state(**changes):
    s=dict(turn=10,floor='D:7',hp=80,max_hp=80,safe=False,status='',
        berserk=False,cooldown=False,confused=False,poisoned=False,on_fire=False,
        monsters={'1':dict(x=1,y=0,threat=3,reachable=True,name='gargoyle')},
        cells={'-1:0':dict(feature='floor',traversable=True),
               '1:0':dict(feature='floor',traversable=True)})
    s.update(changes);return s


CFG=dict(steps=5,turns=100,alpha=.15,gamma=.995)
MEM=dict(last_hp=1.,peak_threat=3,decisions=0,noops=0)


class TrainingTests(unittest.TestCase):
    def test_mask_avoids_approach_attack_cloud_and_unseen(self):
        self.assertEqual(actions(state()),['baseline','wait','melee','berserk','w'])
        self.assertNotIn('tab',actions(state()))
        for field in ('cloud','invisible_monster'):
            s=state();s['cells']['-1:0'][field]=True
            self.assertNotIn('w',actions(s))

    def test_status_masks(self):
        self.assertEqual(actions(state(confused=True)),['baseline','wait'])
        self.assertNotIn('berserk',actions(state(cooldown=True)))
        self.assertNotIn('berserk',actions(state(berserk=True)))
        self.assertNotIn('w',actions(state(status='mesmerised')))
        s=state();s['monsters']['1']['reachable']=False
        self.assertNotIn('melee',actions(s))

    def test_features_have_geometry_and_memory_no_identity(self):
        f=features(state(),MEM)
        self.assertEqual(f['enemy_e'],1)
        self.assertEqual(f['open_w'],1)
        self.assertGreater(features(state(hp=40),MEM)['recent_hp_loss'],0)
        renamed=state();renamed['monsters']['1']['name']='secret identity'
        self.assertEqual(features(renamed,MEM),f)

    def test_eval_selection_does_not_mutate_model(self):
        model={};before=copy.deepcopy(model)
        self.assertEqual(choose(model,state(),MEM,random.Random(1)),'baseline')
        self.assertEqual(model,before)

    def test_update_changes_chosen_weights_with_correct_sign(self):
        model={};update(model,'melee',{'bias':1},-100,0,.9,.1)
        self.assertEqual(model,{'melee':{'bias':-10}})
        update(model,'wait',{'bias':1},0,20,.5,.1)
        self.assertEqual(model['wait']['bias'],1)

    def test_budget_floor_and_death_not_recovery(self):
        self.assertEqual(outcome({'terminal':'death'},'D:7',5,100,0,CFG),'death')
        self.assertEqual(outcome(state(),'D:7',5,2,0,CFG),'budget_truncated')
        self.assertEqual(outcome(state(floor='D:6'),'D:7',1,1,0,CFG),'floor_change')
        self.assertEqual(outcome(state(),'D:7',1,0,8,CFG),'no_turn_stall')
        healed=state(monsters={},safe=True,status='flying')
        self.assertEqual(outcome(healed,'D:7',1,1,0,CFG),'safe_recovery')
        self.assertIsNone(outcome({**healed,'poisoned':True},'D:7',1,1,0,CFG))

    def test_only_recovery_gets_positive_reward(self):
        for label in (None,'death','floor_change','no_turn_stall','budget_truncated'):
            self.assertLessEqual(reward_for(label,0),0)
        self.assertGreater(reward_for('safe_recovery',1),0)
        self.assertEqual(reward_for(None,100),0)
        self.assertEqual(reward_for('death',100),reward_for('death',1))
        self.assertEqual(sum(reward_for(None,1) for _ in range(102))+reward_for('death',1),-100)

    def test_episode_evaluation_is_frozen_and_records_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            class Fake:
                work=root
                def reset(self,case):return state()
                def step(self,action):return {'terminal':'death'}
                def close(self):pass
            model={};before=copy.deepcopy(model);samples=[]
            with patch('train_encounters.Environment',return_value=Fake()):
                r=run_episode(dict(id='x',seed='1',case='unused'),root,'q',model,random.Random(1),CFG,
                              samples=samples)
            self.assertEqual(r['outcome'],'death');self.assertEqual(r['decisions'],1)
            self.assertEqual(model,before)
            self.assertEqual(len(samples),1)
            self.assertEqual(samples[0]['action'],'baseline')
            self.assertIn('baseline',samples[0]['allowed'])
            self.assertNotIn('seed',samples[0]['features'])
            reward=json.loads((root/'rewards.jsonl').read_text())
            self.assertTrue(reward['terminated']);self.assertFalse(reward['truncated'])
            self.assertEqual(reward['bootstrap'],0)

    def test_errors_never_become_deaths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            class Fake:
                def reset(self,case):raise RuntimeError('missing engine')
                def close(self):pass
            with patch('train_encounters.Environment',return_value=Fake()):
                r=run_episode(dict(id='x',seed='1',case='unused'),root,'q',{},random.Random(1),CFG)
            self.assertEqual(r['outcome'],'harness_error');self.assertEqual(r['decisions'],0)

    def test_recovery_handoff_death_is_reported_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            class Fake:
                work=root
                calls=0
                def reset(self,case):return state()
                def step(self,action):
                    self.calls+=1
                    return state(turn=11,monsters={},safe=True) if self.calls==1 else {'terminal':'death'}
                def close(self):pass
            model={}
            with patch('train_encounters.Environment',return_value=Fake()):
                r=run_episode(dict(id='x',seed='1',case='unused'),root,'q',model,random.Random(1),
                              {**CFG,'handoff_steps':10})
            self.assertEqual(r['outcome'],'safe_recovery')
            self.assertEqual(r['handoff']['outcome'],'death')
            self.assertEqual(model,{})
            self.assertEqual(len((root/'rewards.jsonl').read_text().splitlines()),1)

    def test_time_limit_bootstraps_not_terminal_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            class Fake:
                work=root
                def reset(self,case):return state()
                def step(self,action):return state(turn=12)
                def close(self):pass
            model={'baseline':{'bias':2}}
            with patch('train_encounters.Environment',return_value=Fake()), patch('train_encounters.update') as learn:
                r=run_episode(dict(id='x',seed='1',case='unused'),root,'q',model,random.Random(1),
                              {**CFG,'steps':1},training=True)
            self.assertEqual(r['outcome'],'budget_truncated')
            self.assertEqual(learn.call_args.args[4],2)
            self.assertAlmostEqual(learn.call_args.args[5],CFG['gamma']**2)
            row=json.loads((root/'rewards.jsonl').read_text())
            self.assertTrue(row['truncated']);self.assertFalse(row['terminated'])

    def test_handoff_no_turn_loop_is_not_alive_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            class Fake:
                work=root
                def reset(self,case):return state()
                def step(self,action):return state(turn=11,monsters={},safe=True)
                def close(self):pass
            with patch('train_encounters.Environment',return_value=Fake()):
                r=run_episode(dict(id='x',seed='1',case='unused'),root,'q',{},random.Random(1),
                              {**CFG,'handoff_steps':10,'max_noops':2})
            self.assertEqual(r['handoff']['outcome'],'no_turn_stall')
            self.assertEqual(r['handoff']['decisions'],2)

    def test_seed_split_integrity_and_fidelity_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);engine=root/'engine';engine.write_text('engine')
            case=root/'case';case.mkdir();(case/'checkpoint.cs').write_text('save')
            (case/'trial.rc').write_text('rc')
            meta=dict(training_ready=True,seed='123',engine_sha256=sha(engine),
                save_sha256=sha(case/'checkpoint.cs'),rc_sha256=sha(case/'trial.rc'))
            (case/'case.json').write_text(json.dumps(meta))
            e=dict(meta,id='one',eligible=True,case=str(case),split_group='123')
            index=root/'index.json';index.write_text(json.dumps({'cases':[e]}))
            cfg=dict(dataset=str(index),train_cases=['one'],eval_cases=['one'],evaluation_mode='held_out')
            # This fixture tests checkpoint integrity independently of the real
            # seed registry; production partition enforcement has its own tests.
            with patch('train_encounters.ENGINE',engine), patch('train_encounters.enforce'):
                with self.assertRaisesRegex(ValueError,'leakage'):load_cases(cfg)
                cfg['evaluation_mode']='in_sample';load_cases(cfg)
                e['eligible']=False;index.write_text(json.dumps({'cases':[e]}))
                with self.assertRaisesRegex(ValueError,'Unverified'):load_cases(cfg)
                e['eligible']=True;index.write_text(json.dumps({'cases':[e]}))
                (case/'checkpoint.cs').write_text('changed')
                with self.assertRaisesRegex(ValueError,'hash mismatch'):load_cases(cfg)


if __name__=='__main__':unittest.main()
