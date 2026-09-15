"""Safety tests for suite quotas, interrupted writes and output ownership."""
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from ablation_storage import Store, DiskBudgetError


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.store = Store(self.root, 1000, 0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_atomic_replacement_and_interrupted_save(self):
        self.store.atomic('latest.pt', lambda f: f.write(b'old'), 3)
        def interrupted(f):
            f.write(b'new')
            raise OSError('simulated disk full')
        with self.assertRaises(OSError):
            self.store.atomic('latest.pt', interrupted, 10)
        self.assertEqual((self.root/'latest.pt').read_bytes(), b'old')
        self.assertFalse((self.root/'latest.pt.tmp').exists())
        self.store.atomic('latest.pt', lambda f: f.write(b'complete'), 8)
        self.assertEqual((self.root/'latest.pt').read_bytes(), b'complete')

    def test_budget_accounts_for_old_and_temporary(self):
        self.store.atomic('latest.pt', lambda f: f.write(b'a'*600), 600)
        with self.assertRaises(DiskBudgetError):
            self.store.atomic('latest.pt', lambda f: f.write(b'b'*600), 600)
        self.assertEqual((self.root/'latest.pt').stat().st_size, 600)

    def test_serialization_cannot_exceed_reservation(self):
        with self.assertRaises(DiskBudgetError):
            self.store.atomic('latest.pt', lambda f: f.write(b'longer'), 3)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_free_space_reserve(self):
        self.store.reserve_bytes = 950
        with patch('ablation_storage.shutil.disk_usage') as usage:
            usage.return_value.free = 1000
            with self.assertRaises(DiskBudgetError):
                self.store.atomic('latest.pt', lambda f: f.write(b'a'), 100)

    def test_does_not_follow_symlink_or_escape(self):
        with tempfile.TemporaryDirectory() as other:
            path = pathlib.Path(other)/'keep'
            path.write_bytes(b'untouched')
            (self.root/'outside').symlink_to(other, target_is_directory=True)
            for relative in ['outside/keep', '../escape']:
                with self.assertRaises(ValueError):
                    self.store.atomic(relative, lambda f: f.write(b'bad'), 3)
            self.assertEqual(path.read_bytes(), b'untouched')

    def test_removes_only_owned_stale_temporary(self):
        (self.root/'latest.pt.tmp').write_bytes(b'incomplete')
        (self.root/'other.pt').write_bytes(b'keep')
        self.store.atomic('latest.pt', lambda f: f.write(b'ok'), 2)
        self.assertEqual((self.root/'other.pt').read_bytes(), b'keep')
        self.assertEqual((self.root/'latest.pt').read_bytes(), b'ok')


if __name__ == '__main__':
    unittest.main()
