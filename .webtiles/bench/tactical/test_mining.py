import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from mine_encounters import Segmenter, select, validate, capture
from bench import sha


def state(**changes):
    s=dict(turn=10, floor='D:2', hp=30, max_hp=30, safe=True, status='',
           poisoned=False, on_fire=False, monsters={})
    s.update(changes)
    return s


ENEMY={'1':dict(name='orc priest', threat=2)}


class MiningTests(unittest.TestCase):
    def test_recovery_and_los_gap_do_not_split_encounter(self):
        m=Segmenter('1')
        m.observe(state(monsters=ENEMY, safe=False),0)
        m.observe(state(hp=10, poisoned=True),1)
        self.assertEqual(m.cases,[])
        m.observe(state(hp=30, status='berserk cooldown'),2)
        self.assertEqual(m.cases,[])
        m.observe(state(),3)
        self.assertEqual(len(m.cases),1)
        self.assertEqual(m.cases[0]['decisions'],3)
        self.assertIn('large_hp_loss',m.cases[0]['reasons'])

    def test_death_is_terminal_but_budget_is_not_death(self):
        m=Segmenter('1'); m.observe(state(monsters=ENEMY),0)
        m.observe({'terminal':'death'},1)
        self.assertEqual(m.cases[0]['outcome'],'death')
        m.observe(state(monsters=ENEMY),2); m.finish(3,'decision_budget')
        self.assertEqual(m.cases[1]['outcome'],'decision_budget')

    def test_floor_change_not_called_recovery(self):
        m=Segmenter('1');m.observe(state(monsters=ENEMY),0)
        m.observe(state(floor='D:1',hp=4),1)
        self.assertEqual(m.cases[0]['outcome'],'floor_change')

    def test_only_visible_enemies_start_cases(self):
        m=Segmenter('1');m.observe(state(hp=3,poisoned=True),0)
        self.assertIsNone(m.active)

    def test_seed_balanced_selection_prioritizes_death_and_excludes_stalls(self):
        discoveries=[]
        for seed in ('1','2'):
            discoveries.append(dict(trace='trace',trace_sha256='hash',candidates=[
                dict(seed=seed,outcome=o,hp_fraction_loss=0,max_threat=2,decisions=10)
                for o in ('safe_recovery','death','no_turn_stall')]))
        rows=select(discoveries,3)
        self.assertEqual([r['seed'] for r in rows],['1','2','1'])
        self.assertEqual([r['outcome'] for r in rows],['death','death','safe_recovery'])
        self.assertEqual(len({r['id'] for r in rows}),3)

    def test_validation(self):
        cfg=dict(target=30,max_decisions=100,encounters_per_seed=12,jobs=3,seeds=['1','2'])
        validate(cfg)
        for changes in ({'target':0},{'jobs':True},{'seeds':['1','1']},
                        {'seeds':['18446744073709551616']},{'seeds':[1]}):
            with self.assertRaises(ValueError):validate({**cfg,**changes})

    def test_prefix_mismatch_is_rejected_before_checkpointing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.rc';source.write_text('test')
            trace=root/'transitions.jsonl'
            trace.write_text(json.dumps(dict(observation=state(),action='baseline',
                next_observation=state(turn=11)))+'\n')
            row=dict(id='case-1',seed='1',discovery_trace=str(trace),
                     discovery_sha256=sha(trace),start=0,end=1)
            env=Mock(work=root);env.launch.return_value=state(hp=1)
            with patch('mine_encounters.Environment',return_value=env):
                result=capture(root,source,row)
            self.assertFalse(result['training_ready'])
            self.assertIn('prefix divergence',result['error'])
            env.save_checkpoint.assert_not_called()
            env.reset.assert_not_called()
            env.close.assert_called()

    def test_repeatable_but_unfaithful_checkpoint_is_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.rc';source.write_text('test')
            trace=root/'transitions.jsonl'
            trace.write_text(json.dumps(dict(observation=state(),action='baseline',
                next_observation=state(turn=11)))+'\n')
            row=dict(id='case-1',seed='1',discovery_trace=str(trace),
                     discovery_sha256=sha(trace),start=0,end=1,outcome='safe_recovery')
            env=Mock(work=root);env.launch.return_value=state()
            env.reset.return_value=state();env.step.return_value=state(turn=11,hp=1)
            def save(destination,warmup):
                destination.mkdir(); return {}
            env.save_checkpoint.side_effect=save
            with patch('mine_encounters.Environment',return_value=env):
                result=capture(root,source,row)
            self.assertTrue(result['repeatability']['passed'])
            self.assertFalse(result['uninterrupted_fidelity']['passed'])
            self.assertFalse(result['training_ready'])
            self.assertFalse(json.loads((root/'case-1/case/case.json').read_text())['training_ready'])


if __name__=='__main__':unittest.main()
