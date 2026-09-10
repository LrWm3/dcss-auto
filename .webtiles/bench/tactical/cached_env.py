"""Private per-reset copies of verified engine data caches, never save state."""
import argparse
import json
import os
from pathlib import Path
import shutil
from unittest.mock import patch

import bench
from fast_env import FastEnvironment

def cache_inventory(root):
    return {str(p.relative_to(root)):bench.sha(p)
            for folder in ('db','des') for p in sorted((root/folder).rglob('*')) if p.is_file()}

def prepare_cache(worker, destination):
    worker, destination = Path(worker).resolve(), Path(destination).resolve()
    manifest = json.loads((worker/'run.json').read_text())
    if manifest['engine_sha256'] != bench.sha(bench.ENGINE):
        raise ValueError('Cache source engine mismatch')
    destination.mkdir(parents=True, exist_ok=False)
    for folder in ('db','des'):
        shutil.copytree(worker/'saves'/folder, destination/folder)
    files = cache_inventory(destination)
    if not files:
        raise ValueError('Empty cache')
    (destination/'cache.json').write_text(json.dumps(dict(
        source_worker=str(worker), engine_sha256=manifest['engine_sha256'], files=files),indent=2)+'\n')
    return destination

class CachedEnvironment(FastEnvironment):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache = Path(os.environ['DCSS_TACTICAL_CACHE_TEMPLATE']).resolve()
        self.cache_manifest = json.loads((self.cache/'cache.json').read_text())
        if self.cache_manifest['engine_sha256'] != bench.sha(bench.ENGINE):
            raise ValueError('Cache engine mismatch')
        if cache_inventory(self.cache) != self.cache_manifest['files']:
            raise ValueError('Cache checksum mismatch')

    def launch(self, checkpoint=None):
        original_spawn = bench.pexpect.spawn
        def spawn_with_cache(command, args, **kwargs):
            saves = [Path(a.split('=',1)[1]).resolve() for a in args if a.startswith('save_dir=')]
            if len(saves) != 1 or saves[0] != (self.work/'saves').resolve():
                raise ValueError('Unexpected save directory')
            for folder in ('db','des'):
                # Private byte copies. Engines can rebuild stale data without
                # modifying another worker or the shared template.
                shutil.copytree(self.cache/folder, saves[0]/folder)
            return original_spawn(command, args, **kwargs)
        # Existing launch is immutable for historical evidence. The small hook
        # is local to this worker process, not safe for threaded environments.
        with patch.object(bench.pexpect, 'spawn', spawn_with_cache):
            state = super().launch(checkpoint)
        manifest = json.loads((self.work/'run.json').read_text())
        manifest.update(cache_template=str(self.cache),
                        cache_manifest_sha256=bench.sha(self.cache/'cache.json'),
                        cached_adapter_sha256=bench.sha(Path(__file__)))
        (self.work/'run.json').write_text(json.dumps(manifest,indent=2)+'\n')
        return state

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--engine', required=True, type=Path)
    args = parser.parse_args()
    bench.ENGINE = args.engine.resolve()
    print(prepare_cache(args.worker, args.output))
