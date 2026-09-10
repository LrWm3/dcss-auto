"""Training-only pursuit demonstrations, fixed BC warm-start, then masked PPO."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing as mp
import os
from pathlib import Path
import time

os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('MKL_NUM_THREADS', '1')
import numpy as np
import torch
from sb3_contrib import MaskablePPO
from stable_baselines3.common.vec_env import SubprocVecEnv

import bench
from action_env import ActionEnv, fixed_action
from audit_action_episodes import audit
from train_action_ppo import Progress, evaluate


def train_case(task):
    config, root, index, model_path = task
    torch.set_num_threads(1)
    root = Path(root) / f'case-{index:02d}'
    env = ActionEnv(config, root, 'train')
    rows = []
    try:
        obs, _ = env.reset(seed=12000+index, options={'case_index': index})
        model = MaskablePPO.load(model_path, device='cpu') if model_path else None
        for _ in range(env.max_steps):
            mask = env.action_masks()
            if model is None:
                action = fixed_action(env.state, mask, 'pursue')
                rows.append((obs.copy(), mask.copy(), action))
            else:
                action, _ = model.predict(obs, deterministic=True, action_masks=mask)
            obs, _, done, truncated, _ = env.step(action)
            if done or truncated:
                break
        path = env.transport.work / 'episode.json'
        audit(path)
        result = json.loads(path.read_text())
        if rows:
            np.savez_compressed(root/'demonstrations.npz',
                observations=np.stack([r[0] for r in rows]),
                masks=np.stack([r[1] for r in rows]),
                actions=np.asarray([r[2] for r in rows], dtype=np.int64))
            result['demonstrations'] = str(root/'demonstrations.npz')
            result['demonstrations_sha256'] = bench.sha(root/'demonstrations.npz')
        return result
    finally:
        env.close()


def imitation_loss(policy, observations, masks, actions):
    if not bool(masks.gather(1, actions[:, None]).all()):
        raise ValueError('Illegal demonstration label')
    return -policy.get_distribution(observations, action_masks=masks).log_prob(actions).mean()


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def pool_run(fn, tasks):
    with ProcessPoolExecutor(max_workers=6, mp_context=mp.get_context('spawn')) as pool:
        return list(pool.map(fn, tasks))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    config_path = str(args.config.resolve())
    config = json.loads(args.config.read_text())
    if (not config.get('preflight_passed') or config.get('test_used')
            or bench.sha(args.config.parent/'preflight.json') != config['preflight_sha256']):
        raise ValueError('Missing valid preflight')
    root = args.output.resolve(); root.mkdir(parents=True, exist_ok=False)
    sources = ['train_action_imitation.py', 'action_env.py', 'train_action_ppo.py',
               'audit_action_episodes.py', 'rich_features.py', 'goal_controllers.py',
               'cached_env.py', 'fast_env.py']
    (root/'sources').mkdir()
    for name in sources:
        (root/'sources'/name).write_bytes((bench.HERE/name).read_bytes())
    save_json(root/'manifest.json', dict(config=config_path, config_sha256=bench.sha(args.config),
        sources={n: bench.sha(bench.HERE/n) for n in sources}, seed=42, workers=6,
        teacher='action-matched pursue without berserk', bc_epochs=20, bc_batch=128,
        bc_learning_rate=.0003, ppo_steps=6144, validation_selection=False,
        test_used=False, production_export=False, torch=torch.__version__,
        sb3_contrib=__import__('sb3_contrib').__version__))
    count = sum(e['split']=='train' for e in config['cases'])
    print('Collecting training-only demonstrations', flush=True)
    demos = pool_run(train_case, [(config_path, str(root/'demonstrations'), i, None)
                                  for i in range(count)])
    save_json(root/'demonstrations.json', demos)
    arrays = []
    for r in demos:
        if r['split'] != 'train' or bench.sha(Path(r['demonstrations'])) != r['demonstrations_sha256']:
            raise ValueError('Invalid demonstration provenance')
        with np.load(r['demonstrations']) as data:
            arrays.append({k: data[k] for k in data.files})
    observations = torch.from_numpy(np.concatenate([a['observations'] for a in arrays]))
    masks = torch.from_numpy(np.concatenate([a['masks'] for a in arrays]))
    actions = torch.from_numpy(np.concatenate([a['actions'] for a in arrays]))
    print(json.dumps(dict(demonstration_actions=len(actions),
                         outcomes=dict(Counter(r['outcome'] for r in demos)))), flush=True)
    torch.set_num_threads(1)
    env = SubprocVecEnv([lambda i=i: ActionEnv(config_path, root/'train'/f'env-{i}')
                        for i in range(6)], start_method='spawn')
    try:
        model = MaskablePPO('MlpPolicy', env, seed=42, device='cpu', verbose=0,
            n_steps=128, batch_size=128, n_epochs=4, gamma=.995, ent_coef=.01,
            policy_kwargs=dict(net_arch=dict(pi=[128,128], vf=[128,128])))
        optimizer = torch.optim.Adam(model.policy.parameters(), lr=.0003)
        rng = np.random.default_rng(42)
        history = []
        started = time.monotonic()
        for epoch in range(20):
            model.policy.set_training_mode(True)
            order = rng.permutation(len(actions))
            for start in range(0, len(order), 128):
                idx = order[start:start+128]
                loss = imitation_loss(model.policy, observations[idx], masks[idx], actions[idx])
                optimizer.zero_grad(); loss.backward()
                torch.nn.utils.clip_grad_norm_(model.policy.parameters(), .5)
                optimizer.step()
            model.policy.set_training_mode(False)
            correct = 0; loss_sum = 0.
            with torch.no_grad():
                for start in range(0, len(actions), 128):
                    sl = slice(start, start+128)
                    distribution = model.policy.get_distribution(observations[sl], action_masks=masks[sl])
                    correct += int((distribution.get_actions(deterministic=True)==actions[sl]).sum())
                    loss_sum -= float(distribution.log_prob(actions[sl]).sum())
            row = dict(epoch=epoch+1, training_accuracy=correct/len(actions),
                       training_nll=loss_sum/len(actions))
            history.append(row); print(json.dumps(row), flush=True)
        model.save(root/'imitation')
        save_json(root/'imitation.json', dict(history=history, seconds=time.monotonic()-started,
            model_sha256=bench.sha(root/'imitation.zip'), examples=len(actions)))
        # Fixed budget; do not inspect validation or choose a checkpoint first.
        started = time.monotonic()
        model.learn(total_timesteps=6144, callback=Progress(root))
        model.save(root/'finetuned')
        save_json(root/'training.json', dict(steps=model.num_timesteps,
            seconds=time.monotonic()-started, model_sha256=bench.sha(root/'finetuned.zip')))
    except BaseException:
        for process in env.processes:
            if process.is_alive(): process.terminate()
        for process in env.processes: process.join(timeout=5)
        env.closed = True
        raise
    finally:
        if not env.closed: env.close()
    results = {}
    validation_count = sum(e['split']=='validation' for e in config['cases'])
    for name in ('imitation', 'finetuned'):
        print('Evaluating '+name, flush=True)
        model_path = str(root/(name+'.zip'))
        train_results = pool_run(train_case, [(config_path, str(root/name/'training-evaluation'),
                                               i, model_path) for i in range(count)])
        validation = pool_run(evaluate, [(config_path, str(root/name/'validation'),
                                          'ppo', i, model_path) for i in range(validation_count)])
        save_json(root/(name+'-evaluation.json'), dict(train=train_results, validation=validation))
        results[name] = {split: dict(Counter(r['outcome'] for r in rows))
                        for split, rows in [('train', train_results), ('validation', validation)]}
        save_json(root/'summary.json', results); print(json.dumps(results[name]), flush=True)


if __name__ == '__main__':
    main()
