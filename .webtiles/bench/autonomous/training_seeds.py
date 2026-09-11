"""Durable training curriculum: two new seeds and last cycle's lowest score."""
import json
from pathlib import Path
import re
import secrets

from data_split import assert_training_seed
from score_result import has_episode_score
import storage

POLICY = 'two-fresh-plus-previous-lowest-v1'


def plan_cycle(root, cycle):
    root = Path(root)
    path = root/'training_seeds'/f'cycle-{cycle:04d}.json'
    if path.exists():
        plan = json.loads(path.read_text())
        if plan['policy'] != POLICY or plan['cycle'] != cycle:
            raise ValueError('training seed plan mismatch')
        for episode in plan['episodes']:
            assert_training_seed(episode['seed'])
        return plan
    storage.guard()
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = f'cycle-{cycle-1:04d}' if cycle else 'bootstrap'
    scored = []
    for result_path in (root/'replay').glob(f'{previous}-*.result.json'):
        if not re.fullmatch(re.escape(previous)+r'-\d+\.result\.json',result_path.name):
            continue
        result = json.loads(result_path.read_text())
        if result.get('data_role','training') == 'training' and has_episode_score(result):
            assert_training_seed(result['seed'])
            scored.append((result, result_path))
    weakest = min(scored,key=lambda row:(row[0]['score'],int(row[0]['seed']))) if scored else None
    used = set()
    used_rng = set()
    for saved in path.parent.glob('cycle-*.json'):
        for episode in json.loads(saved.read_text())['episodes']:
            used.add(episode['seed'])
            used_rng.add(episode['exploration_seed'])
    # Also avoid historical seeds predating the persistent selection ledger.
    for result_path in (root/'replay').glob('*.result.json'):
        seed = json.loads(result_path.read_text()).get('seed')
        if seed is not None:
            used.add(str(seed))
    config_path = root/'config.json'
    if config_path.exists():
        used.update(str(s) for s in json.loads(config_path.read_text()).get('seeds',[]))
    episodes = []
    for _ in range(2 if weakest else 3):
        while True:
            # Training namespace A cannot intersect confirmation D or audit E,
            # or the fixed five low-valued screen seeds.
            seed = str((0xA << 60) | secrets.randbits(60))
            if seed not in used:
                used.add(seed)
                break
        episodes.append({'seed':seed, 'role':'fresh'})
    if weakest:
        result, result_path = weakest
        episodes.append({'seed':str(result['seed']), 'role':'previous_lowest',
                         'previous_score':result['score'],
                         'source_result':str(result_path.resolve())})
    for episode in episodes:
        while True:
            value = secrets.randbits(64)
            if value not in used_rng:
                used_rng.add(value)
                episode['exploration_seed'] = value
                break
    plan = {'policy':POLICY, 'cycle':cycle, 'source_batch':previous,
            'fallback':None if weakest else 'three fresh seeds; previous batch has no usable training score',
            'episodes':episodes}
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(plan,indent=2)+'\n')
    tmp.replace(path)
    return plan
