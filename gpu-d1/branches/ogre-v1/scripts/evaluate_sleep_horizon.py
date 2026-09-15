#!/usr/bin/env python3
"""Evaluate sleep-policy checkpoints under longer episode deadlines."""
import argparse
import json
import pathlib
import torch
from train_clear import Policy, evaluate
from learn_env_sleep import Env


def checkpoints(run):
    for folder in sorted(run.glob('seed-*')):
        if not folder.is_dir():
            continue
        files = sorted(folder.glob('policy-*.pt'), key=lambda p: int(p.stem.split('-')[1]))
        if files:
            yield folder.name, files[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('runs', nargs='+', type=pathlib.Path)
    ap.add_argument('--output', type=pathlib.Path, required=True)
    ap.add_argument('--limits', default='256,512,1024,2048')
    ap.add_argument('--episodes', type=int, default=2048)
    ap.add_argument('--seed', type=int, default=1200000)
    ap.add_argument('--enemies', type=int, default=8)
    args = ap.parse_args()
    torch.set_num_threads(1)
    limits = [int(x) for x in args.limits.split(',')]
    if any(x < 1 for x in limits):
        raise ValueError('limits must be positive')

    rows = []
    for run in args.runs:
        for limit in limits:
            env = Env(args.episodes, args.enemies, seed=args.seed, limit=limit)
            if limit == limits[0]:
                for mode in ('wait', 'random', 'pursuit'):
                    result = evaluate(env, mode=mode, seed=args.seed)
                    result.update(run=str(run), policy='baseline')
                    rows.append(result)
            for policy_name, checkpoint in checkpoints(run):
                state = torch.load(checkpoint, map_location='cuda', weights_only=False)
                obs_size = state['model']['body.0.weight'].shape[1]
                model = Policy(obs_size).cuda()
                model.load_state_dict(state['model']); model.eval()
                for mode in ('sampled', 'greedy'):
                    result = evaluate(env, model, mode=mode, seed=args.seed)
                    result.update(run=str(run), policy=policy_name, checkpoint=str(checkpoint))
                    rows.append(result)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2, allow_nan=False) + '\n')
    print(json.dumps(rows, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
