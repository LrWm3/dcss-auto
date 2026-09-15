#!/usr/bin/env python3
"""Finalize a D:1 corpus as soon as enough accepted raw exports exist."""
import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import shutil
import time

from collect_d1_corpus import eligible
from compile_corpus import compile_one


def accepted_sources(roots):
    by_seed = {}
    for root in roots:
        for json_path in root.glob('native-*.json'):
            source = json_path.with_suffix('')
            try:
                seed = int(json_path.stem.split('-')[1])
                if seed in by_seed or not eligible(source):
                    continue
                if source.with_suffix('.los').stat().st_size != 5600 * 289:
                    continue
                by_seed[seed] = source
            except (ValueError, OSError, json.JSONDecodeError):
                continue
    return by_seed


def write_splits(output, rows):
    all_dir = output / 'all'
    offset = 0
    for name, size in (('train', 256), ('validation', 32), ('test', 100)):
        split = output / name
        split.mkdir(exist_ok=True)
        split_rows = []
        for row in rows[offset:offset + size]:
            src = all_dir / row['file']
            dst = split / row['file']
            if not dst.exists():
                shutil.copy2(src, dst)
            split_rows.append(row)
        (split / 'manifest.json').write_text(json.dumps({
            'format': 'gpu-d1-d1-floor-corpus-split', 'split': name,
            'count': len(split_rows), 'maps': split_rows,
        }, indent=2) + '\n')
        offset += size


def compile_task(item):
    seed, source, target = item
    if target.exists():
        row = dict(seed=seed, cells=None,
                   sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    else:
        row = compile_one(source, target)
    row['file'] = target.name
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--roots', nargs='+', type=pathlib.Path, required=True)
    ap.add_argument('--count', type=int, default=388)
    ap.add_argument('--output', type=pathlib.Path, required=True)
    ap.add_argument('--poll-seconds', type=float, default=30)
    ap.add_argument('--workers', type=int, default=8)
    args = ap.parse_args()
    roots = [root.resolve() for root in args.roots]
    output = args.output.resolve()
    while True:
        sources = accepted_sources(roots)
        print(f'eligible={len(sources)}/{args.count}', flush=True)
        if len(sources) >= args.count:
            break
        time.sleep(args.poll_seconds)

    output.mkdir(parents=True, exist_ok=True)
    all_dir = output / 'all'
    all_dir.mkdir(exist_ok=True)
    items = [(seed, sources[seed], all_dir / f'map-{seed}.bin')
             for seed in sorted(sources)[:args.count]]
    rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(compile_task, item) for item in items]
        for future in concurrent.futures.as_completed(futures):
            rows.append(future.result())
            if len(rows) % 10 == 0:
                print(f'compiled={len(rows)}/{args.count}', flush=True)
    rows.sort(key=lambda row: row['seed'])
    (output / 'manifest.json').write_text(json.dumps({
        'format': 'gpu-d1-d1-floor-corpus', 'count': len(rows),
        'strict_predicate': 'unsupported_tiles=0 and every map marker has feature id 0',
        'maps': rows, 'seed_order': [row['seed'] for row in rows],
        'source_roots': [str(root) for root in roots],
    }, indent=2) + '\n')
    write_splits(output, rows)
    print(json.dumps({'count': len(rows), 'output': str(output),
                      'splits': {'train': 256, 'validation': 32, 'test': 100}}))


if __name__ == '__main__':
    main()
