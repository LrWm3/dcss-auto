import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock
import pexpect
import numpy as np
from action_env import ACTIONS, legal_mask, frame, FRAME_SIZE, BINS, feature_slot, ActionTransport
from experiment import DIRECTIONS

class ActionTests(unittest.TestCase):
    def test_close_retries_only_verified_dead_child(self):
        env=object.__new__(ActionTransport);env.child=Mock()
        env.child.isalive.side_effect=[True,False]
        error=pexpect.ExceptionPexpect('Could not terminate the child.')
        with patch('action_env.CachedEnvironment.close',side_effect=[error,None]) as close, patch('action_env.time.sleep'):
            env.close()
        self.assertEqual(close.call_count,2)

    def test_close_does_not_hide_live_child(self):
        env=object.__new__(ActionTransport);env.child=Mock()
        env.child.isalive.return_value=True
        error=pexpect.ExceptionPexpect('Could not terminate the child.')
        with patch('action_env.CachedEnvironment.close',side_effect=error), patch('action_env.time.monotonic',side_effect=[0,4]):
            with self.assertRaises(pexpect.ExceptionPexpect):env.close()

    def test_drained_death_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            env=object.__new__(ActionTransport);env.work=Path(tmp);env.seed='123';env.state={'turn':100}
            (env.work/'morgue').mkdir()
            file=env.work/'morgue/morgue-TacticalEustachio-test.txt'
            text='Game seed: 123 (custom seed)\nTacticalEustachio the Chopper (level 7, -2/56 (61) HPs)\nTurns: 100\n'
            file.write_text(text)
            self.assertEqual(env.death_record()['terminal'],'death')
            file.write_text(text.replace('-2/56','2/56'))
            self.assertIsNone(env.death_record())
            file.write_text(text.replace('Turns: 100','Turns: 99'))
            self.assertIsNone(env.death_record())
            file.write_text(text.replace('seed: 123','seed: 124'))
            self.assertIsNone(env.death_record())

    def test_no_macro_actions(self):
        self.assertEqual(len(ACTIONS),10)
        self.assertFalse({'tab','melee','safety','baseline','up'} & set(ACTIONS))

    def test_ally_and_prompt_mask(self):
        cells={str(i):dict(x=x,y=y,traversable=True) for i,(x,y) in enumerate(DIRECTIONS.values())}
        s=dict(known=cells,monsters={},can_berserk=True)
        self.assertTrue(legal_mask(s).all())
        cells['0']['occupied']=True
        cells['1']['unsafe']=True
        m=legal_mask(s)
        self.assertFalse(m[0]);self.assertFalse(m[1]);self.assertTrue(m[-2]);self.assertTrue(m[-1])
        s['monsters']={'1':dict(x=0,y=-1)}
        self.assertTrue(legal_mask(s)[0])
        s['confused']=True
        self.assertFalse(legal_mask(s)[-1])

    def test_features_include_history_without_seed(self):
        s=dict(hp=10,max_hp=20,seed='never used')
        with patch('action_env.features',return_value={'enemy/type=orc':1}):
            a=frame(s,last_action=2,hp_delta=-.1,quiet=10)
            b=frame({**s,'seed':'different'},last_action=2,hp_delta=-.1,quiet=10)
        np.testing.assert_array_equal(a,b)
        self.assertEqual(a.shape,(FRAME_SIZE,))
        self.assertEqual(a[BINS+2],1)
        self.assertEqual(a[-2],.5)
        self.assertEqual(feature_slot('enemy/type=orc'),feature_slot('enemy/type=orc'))

if __name__=='__main__':unittest.main()
