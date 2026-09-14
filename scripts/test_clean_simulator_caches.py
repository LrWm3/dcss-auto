import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import clean_simulator_caches as cleanup


class CacheCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cutoff = time.time() - 3600

    def file(self, name, old=True):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture')
        if old:
            os.utime(path, (self.cutoff - 60, self.cutoff - 60))
        return path

    def selected(self):
        with patch.object(cleanup, 'ROOTS', (self.root,)):
            return [p.relative_to(self.root).as_posix()
                    for _, files in cleanup.candidates(self.cutoff) for p, _ in files]

    def test_only_private_caches(self):
        for name in ('worker/saves/des/map.dsc', 'worker/saves/db/help.db',
                     'worker/saves/hero.cs', 'worker/transitions.jsonl',
                     'template/des/map.dsc', 'template/db/help.db', 'model.pt'):
            self.file(name)
        self.assertEqual(set(self.selected()),
                         {'worker/saves/des/map.dsc', 'worker/saves/db/help.db'})

    def test_unknown_file_preserves_whole_folder(self):
        self.file('worker/saves/db/help.db')
        self.file('worker/saves/db/hero.cs')
        self.assertEqual(self.selected(), [])

    def test_recent_cache_preserved(self):
        self.file('worker/saves/des/map.dsc', old=False)
        self.assertEqual(self.selected(), [])

    def test_symlink_not_followed(self):
        target = self.file('template/db/help.db')
        path = self.root / 'worker/saves/db'
        path.parent.mkdir(parents=True)
        path.symlink_to(target.parent, target_is_directory=True)
        self.assertEqual(self.selected(), [])

    def test_failure_evidence_preserved(self):
        self.file('failures/worker/saves/db/help.db')
        self.assertEqual(self.selected(), [])


if __name__ == '__main__':
    unittest.main()
