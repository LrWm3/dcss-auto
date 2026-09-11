"""Remove disposable heavy files from completed cycles outside an eight-cycle window.

Never remove trees: saves, manifests, results, morgues, failures and models survive.
Unknown/legacy work without a reliable cycle or completion record is preserved.
"""
import argparse
import json
import os
from pathlib import Path
import re
import time

KEEP_CYCLES = 8
HEAVY_NAMES = {'events.jsonl', 'events.jsonl.gz', 'terminal.txt', 'terminal.txt.gz'}
CACHE_SUFFIXES = {'.dsc', '.db', '.idx', '.lux'}


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def prune(root, dry_run=False):
    root = Path(root).resolve()
    completed = int(read(root/'latest_status.json').get('completed_cycles', 0))
    boundary = max(0, completed-KEEP_CYCLES)
    candidates = set()

    def safe(path):
        return (path.is_file() and not path.is_symlink()
                and path.resolve().is_relative_to(root)
                and not any(p.is_symlink() for p in path.parents if p != root))

    def old(name):
        match = re.match(r'^cycle-(\d+)(?:[-.]|$)', name)
        return match is not None and int(match[1]) < boundary

    def heavy(folder):
        if folder.is_symlink() or not folder.is_dir():
            return
        for base, dirs, files in os.walk(folder, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(base)/d).is_symlink()]
            for name in files:
                path = Path(base)/name
                if (name in HEAVY_NAMES or path.suffix in CACHE_SUFFIXES) and safe(path):
                    candidates.add(path)

    # Actor completion sidecars survive replay eviction.
    for folder in (root/'actors').glob('*'):
        result = read(root/'replay'/f'{folder.name}.result.json')
        expired = old(folder.name) or (boundary > 0 and folder.name.startswith('bootstrap-'))
        if expired and result and 'error' not in result:
            heavy(folder)
    for path in (root/'replay').glob('cycle-*.jsonl*'):
        result_path = path.with_suffix('') if path.suffix == '.gz' else path
        result = read(result_path.with_suffix('.result.json'))
        if old(path.name) and result and 'error' not in result and safe(path):
            candidates.add(path)

    # Earlier cycles used the append-only screen ledger, before per-cycle JSON.
    legacy_screens = {}
    ledger = root/'evaluations/paired_seeds.jsonl'
    if ledger.is_file():
        for line in ledger.read_text().splitlines():
            try:
                row = json.loads(line)
                legacy_screens[f"cycle-{int(row['cycle']):04d}"] = row
            except (ValueError, KeyError, TypeError):
                continue
    # Only successful screen records authorize removal of their private work.
    for folder in (root/'evaluations').glob('cycle-*'):
        match = re.fullmatch(r'(cycle-\d+)-(champion|candidate)', folder.name)
        if not match or not old(folder.name):
            continue
        screen = read(root/'evaluations/screens'/f'{match[1]}.json')
        evaluation = screen.get('evaluation', legacy_screens.get(match[1], {}))
        results = evaluation.get(match[2], {}).get('results', [])
        if results and all('error' not in r for r in results):
            heavy(folder)

    for kind in ('confirmations', 'audits'):
        for folder in (root/'evaluations'/kind).glob('*'):
            expired = old(folder.name)
            audit = re.fullmatch(r'after-(\d+)-cycles', folder.name)
            if audit:
                expired = int(audit[1])-1 < boundary
            if not expired or not (folder/'decision.json').is_file():
                continue
            # Preserve any failing individual game's forensic files.
            for path in (folder/'results').glob('*.json'):
                result = read(path)
                if not result or 'error' in result:
                    continue
                role = result.get('policy_version')
                seed = str(result.get('seed', ''))
                if role in ('champion','candidate') and seed.isdigit():
                    heavy(folder/'games'/role/seed)
            heavy(folder/'cutoff_scores')

    for folder in (root/'counterfactual').glob('cycle-*'):
        if old(folder.name) and read(folder/'completed.json').get('complete'):
            heavy(folder)

    records = [{'path':str(p.relative_to(root)), 'bytes':p.stat().st_size}
               for p in sorted(candidates)]
    summary = {'keep_cycles':KEEP_CYCLES, 'completed_cycles':completed,
               'prune_cycles_before':boundary, 'dry_run':dry_run,
               'files':len(records), 'bytes':sum(r['bytes'] for r in records)}
    if not dry_run and records:
        logdir = root/'metrics'; logdir.mkdir(exist_ok=True)
        with (logdir/'heavy_retention.jsonl').open('a') as stream:
            for record in records:
                path = root/record['path']
                if not safe(path):
                    continue
                stream.write(json.dumps({'time':time.time(), 'event':'delete_planned', **record})+'\n')
                stream.flush()
                path.unlink()
                stream.write(json.dumps({'time':time.time(), 'event':'deleted', **record})+'\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    from selection import run_lock
    with run_lock(args.run_dir):
        print(json.dumps(prune(args.run_dir, dry_run=not args.apply), indent=2))
