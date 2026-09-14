import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from general_env import make_rc
from teacher import choose_action


class RestPolicyTests(unittest.TestCase):
    def test_rc_opt_in_preserves_legacy_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.rc'
            for mode in ('0', '1'):
                with patch.dict(os.environ, {'DCSS_REST_ONLY': mode}):
                    make_rc(path)
                self.assertEqual('GENERAL_AGENT_REST_ONLY = true\n' in path.read_text(), mode == '1')

    def test_teacher_uses_legal_rest(self):
        state = {'player': {'hp': 5, 'max_hp': 10},
                 'actions': [{'kind': 'MOVE', 'dx': 1, 'dy': 0}, {'kind': 'REST'}]}
        self.assertEqual(choose_action(state), 1)

    def test_teacher_handles_no_wait_or_rest(self):
        state = {'player': {'hp': 5, 'max_hp': 10},
                 'actions': [{'kind': 'MOVE', 'dx': 1, 'dy': 0}]}
        self.assertEqual(choose_action(state), 0)


if __name__ == '__main__':
    unittest.main()
