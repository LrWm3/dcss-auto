#!/usr/bin/env python3
"""Collect a fixed corpus of supported native D:1 floor layouts.

The native exporter emits the expensive LOS files only for layouts that pass
its terrain predicate. Rejected candidates are removed immediately so a long
seed scan does not consume the workspace with temporary ray tables.
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import time

from compile_corpus import compile_one

ROOT = pathlib.Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'native' / 'source' / 'crawl-gpu-d1'
FIXTURES = ROOT / 'fixtures'


def eligible(source):
    data = json.loads(source.with_suffix('.json').read_text())
    if data.get('unsupported_tiles', 1):
        return False
    marker_path = source.with_suffix('.markers')
    if not marker_path.exists():
        return False
    return all((not line.strip()) or line.split()[0] == '0'
               for line in marker_path.read_text().splitlines())


def clear_source(source):
    for suffix in ('.json', '.markers', '.rays', '.los'):
        source.with_suffix(suffix).unlink(missing_ok=True)


def copy_source(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ('.json', '.markers', '.rays', '.los'):
        shutil.copy2(source.with_suffix(suffix), target.with_suffix(suffix))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--count', type=int, default=388)
    ap.add_argument('--start-seed', type=int, default=1001)
    ap.add_argument('--output', type=pathlib.Path, default=FIXTURES / 'd1-corpus-388')
    args = ap.parse_args()
    args.output = args.output.resolve()
    if args.count < 1:
        raise ValueError('--count must be positive')
    raw = args.output / 'raw'
    compiled = args.output / 'all'
    raw.mkdir(parents=True, exist_ok=True)
    compiled.mkdir(parents=True, exist_ok=True)

    # Reuse already validated exports in the repository, avoiding duplicate
    # seeds while making this corpus self-contained.
    sources = {}
    for root in (FIXTURES, FIXTURES / 'test-export-2', FIXTURES / 'test-export-3'):
        for json_path in root.glob('native-*.json'):
            source = json_path.with_suffix('')
            seed = int(json_path.stem.split('-')[1])
            if seed not in sources and eligible(source):
                target = raw / source.name
                copy_source(source, target)
                sources[seed] = target

    scanned = 0
    seed = args.start_seed
    log_path = args.output / 'export.log'
    with log_path.open('a') as log:
        while len(sources) < args.count:
            if seed in sources:
                seed += 1
                continue
            target = raw / f'native-{seed}'
            # Existing rejected exports are known negatives; do not rerun.
            if target.with_suffix('.json').exists():
                seed += 1
                continue
            command = [str(NATIVE), '-headless', '-no-save', '-no-gdb', '-seed', str(seed),
                       '-script', 'gpu_export', str(target)]
            proc = None
            for attempt in range(5):
                proc = subprocess.run(command, cwd=NATIVE.parent, text=True, capture_output=True)
                if proc.returncode == 0:
                    break
                clear_source(target)
                time.sleep(.25 * (attempt + 1))
            log.write(proc.stdout)
            log.write(proc.stderr)
            if proc.returncode:
                # A small number of native seeds can fail during map
                # generation. Keep the scan reproducible and move on; the
                # accepted-seed manifest is the authoritative corpus.
                print(f'export failed seed={seed} rc={proc.returncode}; skipping', flush=True)
                clear_source(target)
                seed += 1
                continue
            scanned += 1
            if eligible(target):
                sources[seed] = target
                print(f'accepted seed={seed} total={len(sources)}/{args.count}', flush=True)
            else:
                clear_source(target)
            seed += 1
            if scanned % 100 == 0:
                print(f'scanned={scanned} accepted={len(sources)} next_seed={seed}', flush=True)

    rows = []
    for seed in sorted(sources):
        target = compiled / f'map-{seed}.bin'
        if not target.exists():
            row = compile_one(sources[seed], target)
        else:
            row = dict(seed=seed, cells=None,
                       sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        row['file'] = target.name
        rows.append(row)
        if len(rows) % 10 == 0:
            print(f'compiled={len(rows)}/{len(sources)}', flush=True)

    manifest = {
        'format': 'gpu-d1-d1-floor-corpus',
        'count': len(rows),
        'strict_predicate': 'unsupported_tiles=0 and every map marker has feature id 0',
        'maps': rows,
        'seed_order': [row['seed'] for row in rows],
        'source_roots': ['fixtures', 'fixtures/test-export-2', 'fixtures/test-export-3', 'native/source'],
    }
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    # Fixed splits for later experiments; do not use the test split for model
    # selection. The split is by seed and is recorded in each manifest.
    split_specs = (('train', 256), ('validation', 32), ('test', 100))
    offset = 0
    for name, size in split_specs:
        split = args.output / name
        split.mkdir(exist_ok=True)
        split_rows = []
        for row in rows[offset:offset + size]:
            src = compiled / row['file']
            dst = split / row['file']
            if not dst.exists():
                shutil.copy2(src, dst)
            split_rows.append(row)
        (split / 'manifest.json').write_text(json.dumps({
            'format': 'gpu-d1-d1-floor-corpus-split', 'split': name,
            'count': len(split_rows), 'maps': split_rows,
        }, indent=2) + '\n')
        offset += size
    print(json.dumps({'accepted': len(rows), 'scanned_this_run': scanned,
                      'output': str(args.output), 'splits': {'train': 256, 'validation': 32, 'test': 100}}))


if __name__ == '__main__':
    main()
