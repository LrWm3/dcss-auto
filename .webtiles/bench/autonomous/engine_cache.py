"""Verified, private db/des cache copies, adapted from tactical/cached_env.py.

Never copy character saves, share writable files, or patch process-global spawn.
Publication is atomic and locked across both threads and independent processes.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import storage


def inventory(root):
    result = {}
    for folder in ('db', 'des'):
        for path in sorted((root / folder).rglob('*')):
            if path.is_symlink():
                raise ValueError('symlink in engine cache')
            if path.is_file():
                result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def template(engine_hash):
    root = Path(os.environ.get('DCSS_GENERAL_CACHE_ROOT',
                str(Path(__file__).parent / 'artifacts' / 'engine-cache'))).resolve()
    return root / engine_hash


def install(saves, engine_hash):
    source = template(engine_hash)
    if not source.exists():
        return None
    metadata = json.loads((source / 'cache.json').read_text())
    if metadata['engine_sha256'] != engine_hash or inventory(source) != metadata['files']:
        raise ValueError('engine cache checksum mismatch')
    storage.guard()
    for folder in ('db', 'des'):
        shutil.copytree(source / folder, saves / folder)
    if inventory(saves) != metadata['files']:
        raise ValueError('private engine cache copy mismatch')
    return str(source)


def publish(saves, engine_hash):
    destination = template(engine_hash)
    if destination.exists():
        return
    storage.guard()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (destination.parent / (engine_hash + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if destination.exists():
            return
        # TemporaryDirectory cleans only its own private staging directory.
        with tempfile.TemporaryDirectory(prefix='cache-build-', dir=destination.parent) as stage:
            stage = Path(stage)
            payload = stage / 'payload'
            payload.mkdir()
            for folder in ('db', 'des'):
                shutil.copytree(saves / folder, payload / folder)
            files = inventory(payload)
            if not files:
                raise ValueError('empty engine cache')
            (payload / 'cache.json').write_text(json.dumps({
                'engine_sha256':engine_hash, 'files':files, 'source':str(saves)}))
            payload.rename(destination)
