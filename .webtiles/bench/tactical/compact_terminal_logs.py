"""Losslessly compact old, closed terminal logs; preserve all training evidence.

No action traces, checkpoints, morgues or existing archives are changed.
Run without --apply to inspect targets. Restore a log using gzip -d FILE.gz.
"""
import argparse
import gzip
import hashlib
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent/'artifacts'

def opened_files():
    result = set()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            for fd in (proc/'fd').iterdir():
                try:
                    result.add(fd.resolve(strict=True))
                except OSError:
                    pass
        except OSError:
            pass
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    opened = opened_files()
    cutoff = time.time()-3600
    paths = []
    for directory, _, files in os.walk(ROOT):
        if 'terminal.txt' not in files:
            continue
        path = Path(directory)/'terminal.txt'
        if not path.parent.name.startswith('worker-') or path.is_symlink():
            continue
        stat = path.stat()
        if stat.st_mtime >= cutoff or stat.st_size < 65536 or path in opened:
            continue
        if path.with_suffix('.txt.gz').exists():
            continue
        paths.append((path, stat))
    print(json.dumps(dict(files=len(paths), bytes=sum(s.st_size for _,s in paths),
                          apply=args.apply)), flush=True)
    if not args.apply:
        return
    manifest = ROOT/('terminal-compaction-'+time.strftime('%Y%m%d-%H%M%S')+'.jsonl')
    saved = 0
    count = 0
    with manifest.open('x') as log:
        for path, initial in paths:
            archive = path.with_suffix('.txt.gz')
            digest = hashlib.sha256()
            with path.open('rb') as source, archive.open('xb') as raw:
                with gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=1) as dest:
                    while chunk := source.read(1024*1024):
                        digest.update(chunk)
                        dest.write(chunk)
            verified = hashlib.sha256()
            with gzip.open(archive, 'rb') as source:
                while chunk := source.read(1024*1024):
                    verified.update(chunk)
            current = path.stat()
            if (verified.digest() != digest.digest() or current.st_mtime_ns != initial.st_mtime_ns
                    or current.st_size != initial.st_size or current.st_ino != initial.st_ino):
                raise RuntimeError('Verification failed; original retained: '+str(path))
            row = dict(original=str(path), archive=str(archive), sha256=digest.hexdigest(),
                       original_bytes=initial.st_size, archive_bytes=archive.stat().st_size)
            # Persist recovery metadata before removing this exact verified source.
            log.write(json.dumps(row)+'\n')
            log.flush()
            os.fsync(log.fileno())
            path.unlink()
            saved += row['original_bytes']-row['archive_bytes']
            count += 1
            if count % 500 == 0:
                print(json.dumps(dict(compressed=count, saved_bytes=saved)), flush=True)
    print(json.dumps(dict(compressed=count, saved_bytes=saved, manifest=str(manifest))), flush=True)

if __name__ == '__main__':
    main()
