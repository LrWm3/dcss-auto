import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine_cache


class EngineCacheTests(unittest.TestCase):
    def test_private_cache_excludes_saves_and_detects_corruption(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'DCSS_GENERAL_CACHE_ROOT':tmp+'/templates'}):
            source = Path(tmp) / 'source'
            for name in ('db', 'des'):
                (source/name).mkdir(parents=True)
                (source/name/'data').write_text('cache')
            (source/'character.cs').write_text('must not copy')
            engine_cache.publish(source, 'test-engine')
            destination = Path(tmp) / 'private'
            destination.mkdir()
            engine_cache.install(destination, 'test-engine')
            self.assertFalse((destination/'character.cs').exists())
            cached = engine_cache.template('test-engine') / 'db' / 'data'
            self.assertNotEqual(cached.stat().st_ino, (destination/'db'/'data').stat().st_ino)
            (destination/'db'/'data').write_text('modified by private engine')
            self.assertEqual(cached.read_text(), 'cache')
            cached.write_text('corrupt')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                engine_cache.install(Path(tmp)/'other', 'test-engine')


if __name__ == '__main__':
    unittest.main()
