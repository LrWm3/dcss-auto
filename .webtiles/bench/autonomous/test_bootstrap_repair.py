import unittest
import tempfile
import json
from pathlib import Path
import torch
from bootstrap_repair import dropout_recent_actions, navigation_gate, sample_rows, read_training
from structured_features import GLOBAL_DIM, KINDS, STATE_DIM


class BootstrapRepairTests(unittest.TestCase):
    def test_dropout_only_hides_actions(self):
        original=torch.ones(1,STATE_DIM)
        actions=torch.ones(2,3)
        masked,same=dropout_recent_actions((original,actions))
        self.assertIs(same,actions)
        self.assertTrue(torch.all(original==1))
        width=1+len(KINDS)+6+129
        expected=original.clone()
        for i in range(4):
            at=GLOBAL_DIM-4*width+i*width
            expected[:,at+1:at+1+len(KINDS)+2]=0
        self.assertTrue(torch.equal(masked,expected))

    def test_gate_requires_stairs_not_just_depth(self):
        rows=[dict(seed=str(i),score=10,final_level='D:2',steps=100,
                   action_counts={'MOVE':100}) for i in range(5)]
        self.assertFalse(navigation_gate(rows)['accepted'])
        for row in rows[:2]:row['action_counts']['TAKE_STAIRS_DOWN']=1
        self.assertTrue(navigation_gate(rows)['accepted'])
        rows[0]['score']=float('nan')
        self.assertFalse(navigation_gate(rows)['accepted'])

    def test_gate_rejects_wait_loops(self):
        rows=[dict(seed=str(i),score=10,steps=100,truncated=True,
                   action_counts={'WAIT':99,'TAKE_STAIRS_DOWN':1}) for i in range(5)]
        self.assertFalse(navigation_gate(rows)['accepted'])

    def test_no_heldout_labels(self):
        with self.assertRaises(ValueError):
            sample_rows([{'episode_seed':str(0xE<<60)}])

    def test_sampling_does_not_equalize_wait_and_move(self):
        rows=[{'episode_seed':'42','teacher_action_index':0,
               'observation':{'actions':[{'kind':kind}]}}
              for kind in ['MOVE']*900+['WAIT']*100+['TAKE_STAIRS_DOWN']]
        sample=sample_rows(rows,limit=256)
        kinds=[r['observation']['actions'][0]['kind'] for r in sample]
        self.assertLess(kinds.count('WAIT'),60)
        self.assertGreater(kinds.count('MOVE'),190)
        self.assertIn('TAKE_STAIRS_DOWN',kinds)

    def test_incomplete_replay_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            shard=Path(directory)/'episode.jsonl'
            row={'episode_seed':'42','teacher_action_index':0,
                 'observation':{'actions':[{'kind':'WAIT'}]}}
            shard.write_text(json.dumps(row)+'\n')
            self.assertEqual(read_training(directory),[])
            shard.with_suffix('.result.json').write_text('{}')
            self.assertEqual(len(read_training(directory)),1)

    def test_numeric_action_order(self):
        row={'episode_seed':'42','teacher_action_index':0,
             'observation':{'actions':{'2':{'kind':'WAIT'},'1':{'kind':'MOVE'}}}}
        result=sample_rows([row])
        self.assertEqual(result[0]['teacher_action_index'],0)

    def test_rare_stairs_survive_reservoir(self):
        with tempfile.TemporaryDirectory() as directory:
            shard=Path(directory)/'episode.jsonl'
            rows=[{'episode_seed':'42','teacher_action_index':0,
                   'observation':{'actions':[{'kind':kind}]}}
                  for kind in ['MOVE']*1000+['TAKE_STAIRS_DOWN']]
            shard.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            shard.with_suffix('.result.json').write_text('{}')
            sample=read_training(directory,limit=16)
            self.assertEqual(len(sample),16)
            self.assertIn('TAKE_STAIRS_DOWN',
                          [r['observation']['actions'][0]['kind'] for r in sample])

if __name__=='__main__':unittest.main()
