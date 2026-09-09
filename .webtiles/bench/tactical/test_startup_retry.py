import tempfile
import unittest
from pathlib import Path
from startup_retry import retryable,run_with_retry

class StartupRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'terminal.txt').write_text("lair.des:2079: Map 'regret_index_lairdec_grave_grove' has no (possible) exits\n")
        self.row=dict(outcome='harness_error',decisions=0,worker=str(self.root),error='engine exit')

    def test_retry_preserves_failure_and_does_not_inherit_old_error(self):
        calls=[]
        def attempt(i):calls.append(i);return dict(outcome='recovered_quiet',decisions=40)
        result=run_with_retry(attempt,self.row)
        self.assertEqual(calls,[1]);self.assertEqual(result['startup_attempts'],[self.row])
        self.assertNotIn('error',result);self.assertEqual(self.row['outcome'],'harness_error')

    def test_only_one_retry_even_if_failure_repeats(self):
        calls=[]
        def attempt(i):calls.append(i);return dict(self.row)
        r=run_with_retry(attempt);self.assertEqual(calls,[0,1])
        self.assertFalse(retryable(r))
        self.assertEqual(run_with_retry(attempt,r),r);self.assertEqual(calls,[0,1])

    def test_never_retry_gameplay_or_unknown_failures(self):
        for change in ({'outcome':'death'},{'outcome':'budget_truncated'},
                       {'outcome':'unresolved_stall'},{'decisions':1},
                       {'features':{}},{'available':[]}):
            with self.subTest(change=change):self.assertFalse(retryable(dict(self.row,**change)))
        (self.root/'terminal.txt').write_text('Unexpected engine exit')
        self.assertFalse(retryable(self.row))

    def test_observation_marker_prevents_retry(self):
        text=(self.root/'terminal.txt').read_text()
        for marker in ('TBREADY','TBJSON'):
            (self.root/'terminal.txt').write_text(text+marker)
            self.assertFalse(retryable(self.row))

    def test_normal_attempt_runs_once(self):
        calls=[]
        def attempt(i):calls.append(i);return dict(outcome='death',decisions=7)
        self.assertEqual(run_with_retry(attempt)['outcome'],'death');self.assertEqual(calls,[0])

if __name__=='__main__':unittest.main()
