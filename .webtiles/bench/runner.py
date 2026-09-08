"""Append evidence-backed benchmark rows and summarize worst-seed progression."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEEDS = ['6144198052690956201', '13772526223844354029',
         '1760771545328102746', '17908030050512890810', '103583508244309201']
ROUTE = ([f'D:{n}' for n in range(1, 12)] +
         [f'Lair:{n}' for n in range(1, 6)] + ['D:12', 'Orc:1', 'Orc:2'] +
         [f'D:{n}' for n in range(13, 16)])
# Alternative branches occupy the same stage ranks.
STAGES = [('Swamp Shoals', 1, 3), ('Snake Spider', 1, 3),
          ('Swamp Shoals', 4, 4), ('Snake Spider', 4, 4), ('Elf', 1, 2),
          ('Vaults', 1, 4), ('Depths', 1, 4), ('Vaults', 5, 5), ('Zot', 1, 5)]
RANK = {loc: i + 1 for i, loc in enumerate(ROUTE)}
offset = len(ROUTE)
for branches, lo, hi in STAGES:
    for branch in branches.split():
        for depth in range(lo, hi + 1):
            RANK[f'{branch}:{depth}'] = offset + depth - lo + 1
    offset += hi - lo + 1

def digest(data):
    return hashlib.sha256(data).hexdigest()

def record(args):
    raw = Path(args.dump).read_bytes()
    text = raw.decode()
    seed = re.search(r'Game seed: (\d+)', text).group(1)
    if seed not in SEEDS:
        raise ValueError('Not a benchmark seed')
    # Notes table records actually visited floors, not branch annotations.
    locations = set(re.findall(r'^\s*\d+\s*\|\s*([A-Za-z]+:\d+)\s*\|', text, re.M))
    # Current/death location supplements saves with truncated notes.
    for n, branch in re.findall(r'You (?:were|are) on level (\d+) of (?:the )?([^\n.]+)', text):
        branch = {'Dungeon': 'D', 'Lair of Beasts': 'Lair', 'Orcish Mines': 'Orc'}.get(branch, branch)
        locations.add(f'{branch}:{n}')
    known = locations & RANK.keys()
    if not known:
        raise ValueError('No recognized reached milestone')
    best = max(known, key=RANK.get)
    row = dict(version=args.version, character=args.character, seed=seed,
               recorded_at=datetime.now(timezone.utc).isoformat(),
               engine_sha256=args.engine_sha,
               commit=args.commit, rc_sha256=args.rc_sha, outcome=args.outcome,
               reached=best, reached_rank=RANK[best], cleared_prefix=None,
               turns=int(re.search(r'Turns:\s*(\d+)', text).group(1)),
               xl=int(re.search(r'XL:\s*(\d+)', text).group(1)),
               evidence_sha256=digest(raw))
    dest = ROOT / 'evidence' / f'{args.version}-{args.character}.txt'
    row['evidence'] = str(dest.relative_to(ROOT))
    log = ROOT / 'runs.jsonl'
    rows = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    if any(r['version'] == row['version'] and r['seed'] == seed for r in rows):
        raise ValueError('Duplicate version/seed; use a distinct version for replicate batches')
    dest.parent.mkdir(exist_ok=True)
    with dest.open('xb') as f:
        f.write(raw)
    with log.open('a') as f:
        f.write(json.dumps(row, sort_keys=True) + '\n')
    print(json.dumps(row))

def summary():
    groups = {}
    for line in (ROOT / 'runs.jsonl').read_text().splitlines():
        row = json.loads(line)
        groups.setdefault(row['version'], {})[row['seed']] = row
    for version, rows in groups.items():
        complete = set(rows) == set(SEEDS)
        ranks = [rows[s]['reached_rank'] if s in rows else None for s in SEEDS]
        print(version, 'minimum=', min(ranks) if complete else 'INCOMPLETE',
              'ranks=', ranks, 'outcomes=', [rows[s]['outcome'] for s in SEEDS if s in rows])

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('summary')
    p = sub.add_parser('record')
    for key in ('version', 'character', 'outcome'):
        p.add_argument('--' + key, required=True)
    p.add_argument('--commit')
    p.add_argument('--rc-sha')
    p.add_argument('--engine-sha')
    p.add_argument('dump')
    args = parser.parse_args()
    if args.command == 'summary':
        summary()
    else:
        if args.outcome not in ('death', 'paused', 'complete'):
            parser.error('outcome must be death, paused, or complete')
        record(args)
