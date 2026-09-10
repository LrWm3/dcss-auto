import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bench
from fast_env import FastEnvironment, derive_fast

class FastEnvironmentTests(unittest.TestCase):
    def test_derived_case_is_explicit_and_original_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root/'original'
            original.mkdir()
            source = ('  crawl.dump_char()\n  crawl.mpr("TBREADY "..TB.seq.." END")\n'
                      '  crawl.mpr("TBACCEPT END")\n    crawl.redraw_screen()')
            (original/'trial.rc').write_text(source)
            (original/'checkpoint.cs').write_bytes(b'checkpoint')
            (original/'case.json').write_text(json.dumps(dict(
                rc_sha256=bench.sha(original/'trial.rc'),
                save_sha256=bench.sha(original/'checkpoint.cs'), engine_sha256='original',
                training_ready=True)))
            with patch.object(bench, 'ENGINE', original/'checkpoint.cs'):
                derived = derive_fast(original, root/'derived')
            meta = json.loads((derived/'case.json').read_text())
            self.assertFalse(meta['training_ready'])
            self.assertEqual(meta['parent_engine_sha256'], 'original')
            self.assertEqual((original/'trial.rc').read_text(), source)
            self.assertIn('crawl.tactical_emit(tactical_dump)', (derived/'trial.rc').read_text())
            self.assertEqual((derived/'checkpoint.cs').read_bytes(), b'checkpoint')
            (original/'trial.rc').write_text('corrupt')
            with self.assertRaises(ValueError):
                derive_fast(original, root/'bad')

    def test_fifo_frame_and_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = FastEnvironment(tmp)
            class Child:
                pass
            env.child = Child()
            env.buffer = b'\nTBJSON {"seq": 3, "hp": 20}\n'
            self.assertEqual(env.await_state(expected_seq=3)['hp'], 20)
            self.assertIsNone(env.child.delaybeforesend)
            env.buffer = b'\nTBJSON {"seq": 2}\n'
            with self.assertRaises(RuntimeError):
                env.await_state(expected_seq=3)
            env.child = None

    def test_failed_launch_cleans_fifo_and_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = FastEnvironment(tmp)
            old = os.environ.get('DCSS_TACTICAL_OBSERVATION_FIFO')
            with self.assertRaises(FileNotFoundError):
                env.launch(Path(tmp)/'missing')
            self.assertFalse(hasattr(env, 'pipe_fd'))
            self.assertEqual(list(Path(tmp).glob('fifo-*')), [])
            self.assertEqual(os.environ.get('DCSS_TACTICAL_OBSERVATION_FIFO'), old)

if __name__ == '__main__':
    unittest.main()
