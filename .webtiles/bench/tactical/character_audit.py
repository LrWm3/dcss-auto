"""Fail-closed loader for a completed V2 character collection; never fits."""
import argparse
import json
from pathlib import Path
from augmentation_dataset import read, classify, verify_result
from bench import HERE, ROOT, sha
from character_dataset import canonical, intent
from dataset_splits import partition_map
from rich_features import VERSION, features
from run_goals import options
from train_encounters import write


def require(ok, message):
    if not ok:
        raise ValueError(message)


def trajectory(worker, digest=None):
    path = Path(worker) / 'transitions.jsonl'
    if digest is not None:
        require(sha(path) == digest, 'Changed trace: ' + str(path))
    states = []
    with path.open() as stream:
        for line in stream:
            transition = json.loads(line)
            if not states:
                states.append(transition['observation'])
            else:
                require(canonical(states[-1]) == canonical(transition['observation']),
                        'Discontinuous trajectory')
            states.append(transition['next_observation'])
    require(bool(states), 'Empty verification trace')
    return states


def row_identity(row, family, variant, initial):
    require(row['seed'] == family['seed'] == row['split_group'] and
            row['family_id'] == family['id'] and row['case_id'] == variant['id'] and
            row['split'] == family['split'] == 'train', 'Row identity/split mismatch')
    require(row['recipe'] == variant['recipe'], 'Row recipe mismatch')
    require(row.get('feature_version') == VERSION and
            row.get('feature_source_sha256') == sha(HERE / 'rich_features.py') and
            row.get('rich_bridge_sha256') == sha(HERE / 'rich_goal_bridge.lua'),
            'Row feature definition mismatch')
    if 'features' in row:
        require(row['features'] == features(initial), 'Row features differ from verified initial state')
        require(row['available'] == options(initial), 'Row option mask mismatch')


def load(root, mixed=False):
    root = Path(root).resolve()
    manifest = read(root / 'manifest.json')
    for name, digest in manifest['sources'].items():
        require(sha(HERE / name) == digest, 'Collection source changed: ' + name)
    for name, digest in manifest['inputs'].items():
        require(sha(ROOT / name) == digest, 'Collection input changed: ' + name)
    splits = partition_map(read(ROOT / manifest['config']['partitions']))
    entries = {entry['id']: entry for entry in manifest['entries']}
    families = read(root / 'coverage.json')
    require(len(families) == len(entries) and {f['id'] for f in families} == set(entries),
            'Incomplete or duplicate family coverage')
    rows = []
    for family in families:
        entry = entries[family['id']]
        require(family['seed'] == entry['seed'] and
                family['split'] == entry['split'] == splits[entry['seed']] == 'train',
                'Family split mismatch')
        parent = Path(entry['case'])
        for name, key in [('checkpoint.cs', 'save_sha256'), ('trial.rc', 'rc_sha256')]:
            require(sha(parent / name) == entry[key], 'Original parent changed')
        if not family['variants']:
            continue
        neutral = family['neutral']
        reference = read(neutral['reference'])
        require(neutral['passed'] and
                [canonical(s) for s in trajectory(neutral['worker'])] ==
                [canonical(s) for s in reference['states']], 'Neutral replay mismatch')
        baseline = None
        for variant in family['variants']:
            if not variant['replay_verified']:
                continue
            case = Path(variant['case']); meta = read(case / 'case.json')
            require(meta['seed'] == family['seed'] and
                    meta['engine_sha256'] == manifest['engine_sha256'] and
                    meta['character_recipe'] == variant['recipe'], 'Variant provenance mismatch')
            require(sha(case / 'checkpoint.cs') == meta['save_sha256'] == entry['save_sha256'] and
                    sha(case / 'trial.rc') == meta['rc_sha256'], 'Variant bytes changed')
            require(len(variant['workers']) == len(variant['trace_sha256']) == 2,
                    'Missing paired replay')
            a, b = [trajectory(w, h) for w, h in zip(variant['workers'], variant['trace_sha256'])]
            require([canonical(s) for s in a] == [canonical(s) for s in b] and
                    canonical(a[0]) == canonical(variant['initial']), 'Variant replay mismatch')
            if variant['recipe']['axis'] == 'none':
                baseline = a[0]
            require(baseline is not None, 'Missing control')
            intent(baseline, a[0], variant['recipe'])
            checked = []
            for row in variant['rows']:
                row_identity(row, family, variant, a[0])
                worker = Path(row['worker']); run = read(worker / 'run.json')
                require(run['engine_sha256'] == manifest['engine_sha256'] and
                        run['checkpoint_sha256'] == entry['save_sha256'] and
                        run['rc_sha256'] == meta['rc_sha256'], 'Trial provenance mismatch')
                if row.get('trace'):
                    require(sha(Path(row['trace'])) == row['trace_sha256'], 'Trial trace changed')
                    with Path(row['trace']).open() as stream:
                        first = json.loads(next(stream))['observation']
                    require(canonical(first) == canonical(a[0]), 'Trial did not start at verified state')
                checked.append(verify_result(row))
            label = classify(checked)
            if label['complete'] and (not mixed or label['mixed']):
                rows += [r for r in checked if r['outcome'] in ('death', 'recovered_quiet')]
    exported = root / ('mixed-training-rows.json' if mixed else 'training-rows.json')
    require(rows == read(exported), 'Export differs from audited eligible rows')
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('collection', type=Path)
    args = parser.parse_args()
    rows = load(args.collection)
    mixed = load(args.collection, mixed=True)
    report = dict(audited=True, feature_version=VERSION, rows=len(rows), mixed_rows=len(mixed),
                  seeds=sorted({r['seed'] for r in rows}), fitting=False,
                  files={name: sha(args.collection / name) for name in
                         ('manifest.json', 'coverage.json', 'results.json', 'labels.json',
                          'training-rows.json', 'mixed-training-rows.json', 'summary.json')})
    write(args.collection / 'training-index.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
