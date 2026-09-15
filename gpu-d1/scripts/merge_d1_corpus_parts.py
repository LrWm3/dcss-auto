#!/usr/bin/env python3
"""Merge independently scanned/compiled D:1 corpus parts by seed."""
import argparse
import json
import pathlib
import shutil


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parts', nargs='+', type=pathlib.Path, required=True)
    ap.add_argument('--count', type=int, default=388)
    ap.add_argument('--output', type=pathlib.Path, required=True)
    args = ap.parse_args()
    args.parts = [p.resolve() for p in args.parts]
    args.output = args.output.resolve()
    by_seed = {}
    for part in args.parts:
        manifest = json.loads((part / 'manifest.json').read_text())
        for row in manifest['maps']:
            seed = int(row['seed'])
            if seed not in by_seed:
                by_seed[seed] = (part, row)
    if len(by_seed) < args.count:
        raise RuntimeError(f'only {len(by_seed)} unique maps available, need {args.count}')
    rows = []
    all_dir = args.output / 'all'
    all_dir.mkdir(parents=True, exist_ok=True)
    for seed in sorted(by_seed)[:args.count]:
        part, row = by_seed[seed]
        src = part / 'all' / row['file']
        dst = all_dir / row['file']
        if not dst.exists():
            shutil.copy2(src, dst)
        rows.append(row)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'manifest.json').write_text(json.dumps({
        'format': 'gpu-d1-d1-floor-corpus', 'count': len(rows),
        'strict_predicate': 'unsupported_tiles=0 and every map marker has feature id 0',
        'maps': rows, 'seed_order': [row['seed'] for row in rows],
        'parts': [str(p) for p in args.parts],
    }, indent=2) + '\n')
    offset = 0
    for name, size in (('train', 256), ('validation', 32), ('test', 100)):
        split = args.output / name
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
    print(json.dumps({'count': len(rows), 'output': str(args.output),
                      'splits': {'train': 256, 'validation': 32, 'test': 100}}))


if __name__ == '__main__':
    main()
