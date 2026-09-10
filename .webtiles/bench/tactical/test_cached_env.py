import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bench
from cached_env import prepare_cache, CachedEnvironment
from fast_env import FastEnvironment

class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = self.root/'engine'
        self.engine.write_bytes(b'engine')
        self.worker = self.root/'source'
        for folder in ('db','des'):
            (self.worker/'saves'/folder).mkdir(parents=True)
            (self.worker/'saves'/folder/'data').write_bytes(b'cache')
        (self.worker/'saves'/'character.cs').write_bytes(b'never copy')
        (self.worker/'run.json').write_text(json.dumps({'engine_sha256':bench.sha(self.engine)}))
        self.engine_patch = patch.object(bench,'ENGINE',self.engine)
        self.engine_patch.start()
        self.cache = prepare_cache(self.worker,self.root/'template')
        self.env_patch = patch.dict(os.environ,DCSS_TACTICAL_CACHE_TEMPLATE=str(self.cache))
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.engine_patch.stop()
        self.temp.cleanup()

    def test_cache_excludes_character_and_detects_corruption(self):
        self.assertFalse((self.cache/'character.cs').exists())
        CachedEnvironment(self.root/'valid')
        (self.cache/'db'/'data').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'checksum'):
            CachedEnvironment(self.root/'invalid')

    def test_cache_rejects_wrong_engine(self):
        self.engine.write_bytes(b'new engine')
        with self.assertRaisesRegex(ValueError,'engine'):
            CachedEnvironment(self.root/'invalid')

    def test_worker_copies_do_not_share_writes(self):
        env = CachedEnvironment(self.root/'work')
        def fake_launch(instance, checkpoint):
            instance.work = self.root/'private'
            (instance.work/'saves').mkdir(parents=True)
            (instance.work/'run.json').write_text('{}')
            bench.pexpect.spawn('engine',['save_dir='+str(instance.work/'saves')])
            return {'seq':0}
        with patch.object(FastEnvironment,'launch',fake_launch), patch.object(bench.pexpect,'spawn'):
            self.assertEqual(env.launch('case'),{'seq':0})
        copied = env.work/'saves'/'db'/'data'
        copied.write_bytes(b'worker edit')
        self.assertEqual((self.cache/'db'/'data').read_bytes(),b'cache')
        self.assertFalse((env.work/'saves'/'character.cs').exists())

if __name__ == '__main__':
    unittest.main()
