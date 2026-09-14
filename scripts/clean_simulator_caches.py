#!/usr/bin/env python3
"""Remove old PRIVATE saves/db and saves/des caches, never character saves.

Fixed scope: this repository's two artifact roots. Dry run by default.
Shared cache templates, source/build trees and training evidence are untouched.
Run only between simulation jobs. A JSONL deletion audit is always retained.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import time

REPO = Path(__file__).resolve().parents[1]
ROOTS = tuple(REPO / '.webtiles/bench' / kind / 'artifacts'
              for kind in ('tactical', 'autonomous'))
SUFFIXES = {'.db', '.lk', '.dsc', '.idx', '.lux'}


def assert_idle():
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            executable = (proc / 'exe').resolve(strict=True).name
            cwd = (proc / 'cwd').resolve(strict=True)
            if executable.startswith('crawl-') or executable == 'crawl':
                command = (proc / 'cmdline').read_bytes().decode(errors='replace')
                if any(str(root) in command for root in ROOTS):
                    raise RuntimeError(f'Simulator PID {proc.name} is using artifact paths')
                for fd in (proc / 'fd').iterdir():
                    target = fd.resolve()
                    if any(target.is_relative_to(root) for root in ROOTS):
                        raise RuntimeError(f'Simulator PID {proc.name} has an artifact open')
            if any(cwd.is_relative_to(root) for root in ROOTS):
                raise RuntimeError(f'Process {proc.name} is using an artifact directory')
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            continue


def files_in(folder, cutoff):
    result = []
    for base, dirs, names in os.walk(folder, followlinks=False):
        if any((Path(base) / d).is_symlink() for d in dirs):
            return []
        for name in names:
            path = Path(base) / name
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or path.suffix not in SUFFIXES
                    or info.st_mtime >= cutoff):
                return []  # unknown, symlink or recently used cache: keep whole folder
            result.append((path, info))
    return result


def candidates(cutoff):
    for root in ROOTS:
        if not root.is_dir() or root.is_symlink():
            continue
        for base, dirs, _ in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()
                       and d not in ('failures', 'crashes', 'invalid_states')]
            if Path(base).name != 'saves':
                continue
            for name in ('db', 'des'):
                if name not in dirs:
                    continue
                dirs.remove(name)
                folder = Path(base) / name
                files = files_in(folder, cutoff)
                if files:
                    yield folder, files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    assert_idle()
    cutoff = time.time() - 3600
    audit = REPO / '.webtiles/bench/maintenance'
    audit.mkdir(exist_ok=True)
    destination = audit / (time.strftime('%Y%m%d-%H%M%S') +
                           ('-cache-delete.jsonl' if args.apply else '-cache-plan.jsonl'))
    folders = count = size = 0
    with destination.open('x') as log:
        for folder, files in candidates(cutoff):
            row = {'path': str(folder.relative_to(REPO)), 'files': len(files),
                   'bytes': sum(info.st_size for _, info in files),
                   'reason': 'regenerable private engine cache', 'apply': args.apply}
            if args.apply:
                if folders % 500 == 0:
                    assert_idle()
                log.write(json.dumps({'event': 'delete_planned', **row}) + '\n')
                log.flush()
                for path, before in files:
                    now = path.lstat()
                    if (now.st_ino, now.st_size, now.st_mtime_ns) != (
                            before.st_ino, before.st_size, before.st_mtime_ns):
                        raise RuntimeError(f'File changed during cleanup: {path}')
                    path.unlink()
                row['event'] = 'deleted'
            else:
                row['event'] = 'candidate'
            log.write(json.dumps(row) + '\n')
            folders += 1
            count += row['files']
            size += row['bytes']
            if folders % 2000 == 0:
                print(json.dumps({'folders': folders, 'GiB': round(size / 1024**3, 2)}), flush=True)
    print(json.dumps({'apply': args.apply, 'folders': folders, 'files': count,
                      'GiB': size / 1024**3, 'audit': str(destination)}), flush=True)


if __name__ == '__main__':
    main()
