import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from general_env import GeneralEnvironment
from teacher import choose_action


class CheckpointTests(unittest.TestCase):
    def test_snapshot_requires_explicit_acknowledgement(self):
        with tempfile.TemporaryDirectory() as tmp:
            env=GeneralEnvironment(tmp)
            env.state={'seq':7}
            env.buffer=b'GJSON {"seq":7,"actions":[]}\n'
            with self.assertRaisesRegex(RuntimeError,'acknowledgement'):
                env.await_state(expected_seq=7,snapshot=True)
            env.buffer=b'GSAVED {"seq":7}\n'
            self.assertEqual(env.await_state(expected_seq=7,snapshot=True),{'seq':7})

    @unittest.skipUnless(os.environ.get('CRAWL_STORAGE_LIVE_TEST'),'opt-in engine test')
    def test_in_place_save_keeps_pid_rng_and_restorable_future(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'DCSS_GENERAL_RNG_DIAGNOSTICS':'1'}):
            root=Path(tmp)
            live=GeneralEnvironment(root/'live'); clone=GeneralEnvironment(root/'clone')
            try:
                state=live.launch()
                if not state.get('snapshot_in_place'):
                    self.skipTest('engine predates in-place snapshots')
                for _ in range(5):
                    state=live.step(choose_action(state))
                pid=live.child.pid
                saved=live.save_state(root/'case')
                self.assertEqual(saved['save_mode'],'in_place')
                self.assertEqual(live.child.pid,pid)
                self.assertEqual(clone.launch(root/'case'),state)
                for _ in range(8):
                    action=state['actions'][choose_action(state)]
                    state=live.step(action)
                    self.assertEqual(clone.step(action),state)
            finally:
                live.close(); clone.close()
