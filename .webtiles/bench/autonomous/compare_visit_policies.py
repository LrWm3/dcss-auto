"""Fresh paired REST/visit-policy screen; no training or promotion."""
import os
for key in ('DCSS_HEALTH_FEATURES', 'DCSS_REST_ONLY', 'DCSS_VISIT_MEMORY'):
    os.environ[key] = '1'
os.environ['DCSS_REPRESENTATION'] = 'spatial-v6'
import argparse
import concurrent.futures
import json
import math
import random
import statistics
from pathlib import Path
import torch
from bootstrap_repair import write
from collect import run_episode
from general_env import sha, ENGINE
from model import load_model
from score_result import has_episode_score
import storage


def summarize(rows, seeds, complete=False):
    groups = {label: [r for r in rows if r['comparison_policy'] == label]
              for label in ('baseline', 'candidate')}
    result = {'completed_games': len(rows), 'total_games': 2*len(seeds),
              'phase': 'complete' if complete else 'running', 'promoted': False}
    for label, values in groups.items():
        valid = [r for r in values if 'error' not in r and has_episode_score(r)
                 and isinstance(r.get('score'), (int, float)) and math.isfinite(r['score'])]
        scores = [r['score'] for r in valid]
        result[label] = {'games': len(values), 'valid_scores': len(scores),
            'errors_or_missing_scores': len(values)-len(valid),
            'mean_score': statistics.mean(scores) if scores else None,
            'median_score': statistics.median(scores) if scores else None,
            'max_score': max(scores) if scores else None,
            'descents': sum(r.get('action_counts', {}).get('TAKE_STAIRS_DOWN', 0)>0 for r in valid),
            'deaths': sum(r.get('terminal_kind') == 'death' for r in valid),
            'cutoffs': sum(bool(r.get('truncated')) for r in valid)}
        training = [r['training_score'] for r in valid if r.get('training_score') is not None]
        result[label]['mean_training_score'] = statistics.mean(training) if training and len(training) == len(valid) else None
        result[label]['mean_native_score'] = result[label]['mean_score']
    indexed = {(r['comparison_policy'], r['seed']): r for r in rows}
    pairs = []
    for seed in seeds:
        a, b = indexed.get(('baseline', seed)), indexed.get(('candidate', seed))
        if a and b and all('error' not in r and has_episode_score(r)
                and isinstance(r.get('score'), (int, float)) and math.isfinite(r['score']) for r in (a,b)):
            pairs.append({'seed': seed, 'baseline': a['score'], 'candidate': b['score'],
                          'difference': b['score']-a['score']})
    differences = [p['difference'] for p in pairs]
    result['paired'] = {'valid_pairs': len(pairs),
        'mean_score_difference': statistics.mean(differences) if differences else None,
        'better': sum(d>0 for d in differences), 'tied': sum(d==0 for d in differences),
        'worse': sum(d<0 for d in differences)}
    if complete and differences:
        rng = random.Random(47)
        boot = sorted(statistics.mean(rng.choices(differences, k=len(differences))) for _ in range(5000))
        result['paired']['descriptive_bootstrap_95_interval'] = [boot[125], boot[4874]]
        result['paired']['all_pairs_valid'] = len(pairs) == len(seeds)
    return result, pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(1)
    root = args.output.resolve(); root.mkdir(parents=True, exist_ok=True)
    storage.configure(root)
    models = {'baseline': args.baseline.resolve(), 'candidate': args.candidate.resolve()}
    rng = random.Random(2026091301)
    seeds = []
    while len(seeds) < 40:
        seed = str((0xC << 60) | rng.getrandbits(60))
        if seed not in seeds:
            seeds.append(seed)
    config = {'seeds': seeds, 'steps_per_floor': 2000, 'total_decisions': 2000,
              'epsilon': 0, 'workers': 6, 'training': False, 'engine_sha256': sha(ENGINE),
              'models': {k: {'path': str(v), 'sha256': sha(v)} for k,v in models.items()},
              'source_hashes': {p: sha(Path(__file__).parent/p) for p in
                  ('compare_visit_policies.py', 'collect.py', 'general_env.py', 'general_bridge.lua',
                   'structured_bridge.lua', 'structured_features.py', 'visit_memory.py', 'observation_history.py')}}
    if (root/'config.json').exists():
        if json.loads((root/'config.json').read_text()) != config:
            raise ValueError('resume configuration mismatch')
    else:
        write(root/'config.json', config)
    for path in models.values():
        load_model(path)
    def run(task):
        label, i, seed = task
        path = root/'results'/f'{label}-{i}.json'
        if path.exists():
            saved = json.loads(path.read_text())
            if saved['seed'] != seed or saved['comparison_policy'] != label:
                raise ValueError('cached episode identity mismatch')
            return saved
        try:
            r = run_episode(root/'games'/f'{label}-{i}', seed, 2000,
                    model_path=models[label], epsilon=0, snapshot=False,
                    total_steps=2000, data_role='screen')
        except Exception as exc:
            r = {'error': repr(exc)}
        r.update(seed=seed, comparison_policy=label)
        write(path, r)
        return r
    rows = []
    write(root/'latest_status.json', summarize(rows, seeds)[0])
    tasks = [(label, i, seed) for i,seed in enumerate(seeds) for label in models]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for future in concurrent.futures.as_completed([pool.submit(run, task) for task in tasks]):
            rows.append(future.result())
            write(root/'latest_status.json', summarize(rows, seeds)[0])
    status, pairs = summarize(rows, seeds, complete=True)
    write(root/'paired_scores.json', pairs)
    write(root/'results.json', sorted(rows, key=lambda r: (r['seed'], r['comparison_policy'])))
    write(root/'latest_status.json', status)


if __name__ == '__main__':
    main()
