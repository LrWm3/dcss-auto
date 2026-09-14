#!/usr/bin/env python3
"""Losslessly gzip old tactical worker traces; default is a dry run.

Preserve raw source until gzip is read back and SHA256 verified. Models,
datasets, saved states, result summaries and general-policy replay are excluded.
Historical tools requiring the original filename can use gzip -dk FILE.jsonl.gz.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import time

from clean_simulator_caches import REPO, assert_idle

ROOT = REPO / '.webtiles/bench/tactical/artifacts'
NAMES = {'transitions.jsonl', 'events.jsonl'}


def candidates():
    cutoff = time.time() - 24 * 3600
    for base, dirs, files in os.walk(ROOT, followlinks=False):
        dirs[:] = [d for d in dirs if d not in ('saves', 'db', 'des', 'failures', 'crashes')
                   and not (Path(base) / d).is_symlink()]
        folder = Path(base)
        if not folder.name.startswith('worker-'):
            continue
        for name in sorted(NAMES.intersection(files)):
            path = folder / name
            if path.is_symlink() or Path(str(path) + '.gz').exists():
                continue
            info = path.stat()
            if info.st_mtime < cutoff and info.st_size >= 65536:
                yield path


def compact(path):
    before = path.stat()
    dest = Path(str(path) + '.gz')
    digest = hashlib.sha256()
    # Exclusive creation prevents overwriting an existing archive.
    with path.open('rb') as source, dest.open('xb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=1) as out:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                out.write(chunk)
        raw.flush()
        os.fsync(raw.fileno())
    check = hashlib.sha256()
    with gzip.open(dest, 'rb') as stream:
        while chunk := stream.read(1024 * 1024):
            check.update(chunk)
    now = path.stat()
    if (check.digest() != digest.digest() or
            (now.st_ino, now.st_size, now.st_mtime_ns) !=
            (before.st_ino, before.st_size, before.st_mtime_ns)):
        raise RuntimeError(f'Verification failed, source retained: {path}')
    return {'path': str(path.relative_to(REPO)), 'archive': str(dest.relative_to(REPO)),
            'sha256': digest.hexdigest(), 'bytes': before.st_size,
            'archive_bytes': dest.stat().st_size, 'mtime_ns': before.st_mtime_ns}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--workers', type=int, default=4, choices=range(1, 9))
    args = parser.parse_args()
    assert_idle()
    paths = list(candidates())
    print(json.dumps({'files': len(paths), 'GiB': sum(p.stat().st_size for p in paths) / 1024**3,
                      'apply': args.apply}), flush=True)
    if not args.apply:
        return
    audit = REPO / '.webtiles/bench/maintenance'
    audit.mkdir(exist_ok=True)
    logpath = audit / (time.strftime('%Y%m%d-%H%M%S') + '-trace-compaction.jsonl')
    count = saved = 0
    with logpath.open('x') as log, ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(compact, paths):
            # Durable recovery metadata is written before exact-source unlink.
            log.write(json.dumps({'event': 'verified', **row}) + '\n')
            log.flush()
            os.fsync(log.fileno())
            source = REPO / row['path']
            now = source.stat()
            if now.st_size != row['bytes'] or now.st_mtime_ns != row['mtime_ns']:
                raise RuntimeError(f'Source changed; original retained: {source}')
            source.unlink()
            count += 1
            saved += row['bytes'] - row['archive_bytes']
            if count % 500 == 0:
                assert_idle()
                print(json.dumps({'compressed': count, 'saved_GiB': saved / 1024**3}), flush=True)
    print(json.dumps({'compressed': count, 'saved_GiB': saved / 1024**3,
                      'audit': str(logpath)}), flush=True)


if __name__ == '__main__':
    main()
