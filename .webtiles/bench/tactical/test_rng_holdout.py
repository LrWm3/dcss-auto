import hashlib
import tempfile
from pathlib import Path
import tarfile
import unittest
from evaluate_rng_holdout import pack, rates


class RngHoldoutTests(unittest.TestCase):
    def test_missing_and_stalled_are_unknown_not_deaths(self):
        vs=[dict(rows=[dict(evaluator='candidate',outcome='recovered_quiet',evidence_verified=True)]),
            dict(rows=[dict(evaluator='candidate',outcome='death',evidence_verified=True)]),
            dict(rows=[dict(evaluator='candidate',outcome='unresolved_stall',evidence_verified=False)])]
        r=rates(vs)['candidate']
        self.assertEqual((r['wins'],r['deaths'],r['unknown']),(1,1,8))
        self.assertEqual((r['recovery_rate_lower'],r['recovery_rate_upper']),(.1,.9))
        self.assertEqual(rates(vs)['pursue_no_berserk']['unknown'],10)

    def test_archive_preserves_all_worker_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            worker=Path(folder)/'worker-test';worker.mkdir()
            (worker/'run.json').write_text('{}')
            (worker/'saves').mkdir();(worker/'saves'/'test.cs').write_bytes(bytes(range(256)))
            result=pack(worker)
            self.assertFalse(worker.exists())
            self.assertEqual(hashlib.sha256(Path(result['path']).read_bytes()).hexdigest(),result['sha256'])
            with tarfile.open(result['path']) as tar:
                self.assertEqual(tar.extractfile('worker-test/saves/test.cs').read(),bytes(range(256)))


if __name__=='__main__': unittest.main()
