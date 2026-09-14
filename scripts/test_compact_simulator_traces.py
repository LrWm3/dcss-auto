import gzip
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import compact_simulator_traces as traces


class TraceCompactionTests(unittest.TestCase):
    def test_verified_archive_is_lossless_and_source_remains_until_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / 'worker-test'
            worker.mkdir()
            path = worker / 'transitions.jsonl'
            content = b'{"observation": [1,2,3], "action": "move"}\n' * 3000
            path.write_bytes(content)
            with patch.object(traces, 'REPO', root):
                row = traces.compact(path)
            self.assertTrue(path.exists())
            self.assertEqual(gzip.decompress((root / row['archive']).read_bytes()), content)
            self.assertEqual(row['sha256'], hashlib.sha256(content).hexdigest())
            self.assertLess(row['archive_bytes'], row['bytes'])
            with patch.object(traces, 'REPO', root):
                with self.assertRaises(FileExistsError):
                    traces.compact(path)

    def test_dataset_and_recent_worker_are_not_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('worker-old/transitions.jsonl', 'worker-new/transitions.jsonl',
                         'dataset/transitions.jsonl', 'worker-old/saves/hero.cs'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'x' * 70000)
                if 'worker-new' not in name:
                    os.utime(path, (1, 1))
            with patch.object(traces, 'ROOT', root):
                self.assertEqual(list(traces.candidates()), [root / 'worker-old/transitions.jsonl'])


if __name__ == '__main__':
    unittest.main()
