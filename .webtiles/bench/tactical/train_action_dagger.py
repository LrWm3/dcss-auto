"""Combat-weighted imitation with training-only learner-state teacher labels."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path

os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('MKL_NUM_THREADS', '1')
import numpy as np
import torch
from sb3_contrib import MaskablePPO

import bench
from action_env import ACTIONS, ActionEnv, fixed_action
from audit_action_episodes import audit
from train_action_imitation import pool_run, save_json, train_case
from train_action_ppo import evaluate


def stratum(state, teacher):
    if teacher != ACTIONS.index('wait'):
        return 0  # moves / attacks
    return 1 if state.get('monsters') or state.get('unseen') else 2


def sample_weights(groups, mistakes):
    """60% movement/attack, 20% threatened wait, 20% other wait when present."""
    weights = np.zeros(len(groups), dtype=np.float64)
    for group, mass in enumerate((.6, .2, .2)):
        selected = groups == group
        if selected.any():
            local = 1. + mistakes[selected].astype(float)
            weights[selected] = mass * local / local.sum()
    if not weights.sum():
        raise ValueError('Empty training data')
    return weights / weights.sum()


def collect(task):
    config, root, index, checkpoint = task
    torch.set_num_threads(1)
    root = Path(root)/f'case-{index:02d}'
    env = ActionEnv(config, root, 'train')
    rows = []
    try:
        obs, _ = env.reset(seed=15000+index, options={'case_index': index})
        model = MaskablePPO.load(checkpoint, device='cpu')
        for _ in range(env.max_steps):
            mask = env.action_masks()
            teacher = fixed_action(env.state, mask, 'pursue')
            learner, _ = model.predict(obs, deterministic=True, action_masks=mask)
            learner = int(learner)
            rows.append((obs.copy(), mask.copy(), teacher, stratum(env.state, teacher), learner))
            # Execute the learner, not the teacher: labels correct its own states.
            obs, _, done, truncated, _ = env.step(learner)
            if done or truncated:
                break
        audit(env.transport.work/'episode.json')
        result = json.loads((env.transport.work/'episode.json').read_text())
        np.savez_compressed(root/'labels.npz', observations=np.stack([r[0] for r in rows]),
            masks=np.stack([r[1] for r in rows]), actions=np.asarray([r[2] for r in rows]),
            groups=np.asarray([r[3] for r in rows]), executed=np.asarray([r[4] for r in rows]))
        result.update(labels=str(root/'labels.npz'), labels_sha256=bench.sha(root/'labels.npz'),
                      disagreements=sum(r[2]!=r[4] for r in rows))
        return result
    finally:
        env.close()


def load_labels(result):
    if result['split'] != 'train' or bench.sha(Path(result['labels'])) != result['labels_sha256']:
        raise ValueError('Nontraining or changed labels')
    with np.load(result['labels']) as data:
        return {k: data[k] for k in data.files}


def fit(model, arrays, epochs, seed):
    data = {k: np.concatenate([a[k] for a in arrays]) for k in arrays[0]}
    probabilities = sample_weights(data['groups'], data['actions']!=data['executed'])
    optimizer = torch.optim.Adam(model.policy.parameters(), lr=.0003)
    rng = np.random.default_rng(seed)
    model.policy.set_training_mode(True)
    for _ in range(epochs):
        # Fixed draws per epoch, not an unbounded resampling-to-success loop.
        for start in range(0, len(probabilities), 128):
            idx = rng.choice(len(probabilities), size=min(128,len(probabilities)-start), p=probabilities)
            obs = torch.from_numpy(data['observations'][idx])
            masks = torch.from_numpy(data['masks'][idx])
            actions = torch.from_numpy(data['actions'][idx]).long()
            if not bool(masks.gather(1, actions[:,None]).all()):
                raise ValueError('Illegal teacher action')
            loss = -model.policy.get_distribution(obs, action_masks=masks).log_prob(actions).mean()
            optimizer.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.policy.parameters(), .5)
            optimizer.step()
    model.policy.set_training_mode(False)
    correct = Counter(); total = Counter()
    for start in range(0,len(probabilities),128):
        sl = slice(start,start+128)
        predicted, _ = model.predict(data['observations'][sl], deterministic=True,
                                     action_masks=data['masks'][sl])
        for group in range(3):
            selected = data['groups'][sl]==group
            total[group] += int(selected.sum())
            correct[group] += int(((predicted==data['actions'][sl]) & selected).sum())
    return dict(examples=len(probabilities), epochs=epochs, correct=dict(correct), total=dict(total))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(); parent = args.parent.resolve()
    previous = json.loads((parent/'manifest.json').read_text())
    config_path = previous['config']; config = json.loads(Path(config_path).read_text())
    if bench.sha(Path(config_path)) != previous['config_sha256'] or previous['test_used']:
        raise ValueError('Parent provenance changed')
    init = json.loads((parent/'imitation.json').read_text())
    if bench.sha(parent/'imitation.zip') != init['model_sha256']:
        raise ValueError('Initialization changed')
    root = args.output.resolve(); root.mkdir(parents=True,exist_ok=False)
    sources = ['train_action_dagger.py','action_env.py','train_action_imitation.py',
               'train_action_ppo.py','audit_action_episodes.py','goal_controllers.py','rich_features.py']
    (root/'sources').mkdir()
    for name in sources:
        (root/'sources'/name).write_bytes((bench.HERE/name).read_bytes())
    save_json(root/'manifest.json', dict(parent=str(parent), parent_manifest_sha256=bench.sha(parent/'manifest.json'),
        config=config_path, config_sha256=bench.sha(Path(config_path)), initialization_sha256=init['model_sha256'],
        sources={n:bench.sha(bench.HERE/n) for n in sources}, rounds=3, initial_epochs=20,
        epochs_per_round=10, group_mass=[.6,.2,.2], disagreement_multiplier=2,
        learner_execution_probability=1, teacher='pursue without berserk', seed=42,
        test_used=False, validation_selection=False, production_export=False))
    arrays = []
    # Reuse audited training demonstrations, never validation trajectories.
    for r in json.loads((parent/'demonstrations.json').read_text()):
        if r['split']!='train' or bench.sha(Path(r['demonstrations'])) != r['demonstrations_sha256']:
            raise ValueError('Invalid training demonstrations')
        audit(Path(r['worker'])/'episode.json')
        with np.load(r['demonstrations']) as data:
            a = {k:data[k] for k in data.files}
        events = [json.loads(line) for line in (Path(r['worker'])/'events.jsonl').read_text().splitlines()]
        states = [events[0]['initial_observation']] + [e['next_observation'] for e in events[1:-1]]
        if len(states)!=len(a['actions']): raise ValueError('Demonstration length mismatch')
        a['groups'] = np.asarray([stratum(s,int(t)) for s,t in zip(states,a['actions'])])
        a['executed'] = a['actions'].copy(); arrays.append(a)
    torch.set_num_threads(1); torch.manual_seed(42)
    model = MaskablePPO.load(parent/'imitation.zip', device='cpu')
    stats = fit(model,arrays,20,42); model.save(root/'balanced')
    save_json(root/'balanced-fit.json',stats); print(json.dumps(stats),flush=True)
    count = sum(e['split']=='train' for e in config['cases'])
    checkpoint = root/'balanced.zip'
    for round_id in range(1,4):
        print(f'Collecting learner-state labels: round {round_id}',flush=True)
        rows = pool_run(collect, [(config_path,str(root/f'round-{round_id}'),i,str(checkpoint)) for i in range(count)])
        save_json(root/f'round-{round_id}.json',rows)
        arrays.extend(load_labels(r) for r in rows)
        stats = fit(model,arrays,10,42+round_id)
        checkpoint = root/f'round-{round_id}.zip'; model.save(checkpoint)
        stats.update(model_sha256=bench.sha(checkpoint), outcomes=dict(Counter(r['outcome'] for r in rows)),
                     disagreements=sum(r['disagreements'] for r in rows))
        save_json(root/f'round-{round_id}-fit.json',stats); print(json.dumps(stats),flush=True)
    results = {}
    for name in ('balanced','round-3'):
        print('Frozen evaluation: '+name,flush=True)
        checkpoint = str(root/(name+'.zip'))
        train = pool_run(train_case,[(config_path,str(root/name/'train-evaluation'),i,checkpoint) for i in range(count)])
        val = pool_run(evaluate,[(config_path,str(root/name/'validation'),'ppo',i,checkpoint)
                                for i in range(sum(e['split']=='validation' for e in config['cases']))])
        save_json(root/(name+'-evaluation.json'),dict(train=train,validation=val))
        results[name] = {split:dict(Counter(r['outcome'] for r in rows))
                         for split,rows in [('train',train),('validation',val)]}
        save_json(root/'summary.json',results); print(json.dumps(results[name]),flush=True)


if __name__=='__main__': main()
