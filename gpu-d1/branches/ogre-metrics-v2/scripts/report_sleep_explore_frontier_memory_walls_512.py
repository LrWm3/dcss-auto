#!/usr/bin/env python3
"""Fresh-suite report for corrected frontier memory with a 512-decision deadline."""
import argparse
import json
import pathlib
import torch
from train_clear import Policy, evaluate
from learn_env_sleep_explore_frontier_memory_walls_512 import Env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run', type=pathlib.Path)
    ap.add_argument('--output', type=pathlib.Path, required=True)
    ap.add_argument('--episodes', type=int, default=2048)
    ap.add_argument('--seed', type=int, default=1200000)
    ap.add_argument('--enemies', type=int, default=8)
    args = ap.parse_args()
    torch.set_num_threads(1)
    env = Env(args.episodes, args.enemies, seed=args.seed)
    rows = [evaluate(env, mode=mode, seed=args.seed) for mode in ('wait', 'random', 'pursuit')]
    for folder in sorted(args.run.glob('seed-*')):
        if not folder.is_dir():
            continue
        checkpoints = sorted(folder.glob('policy-*.pt'), key=lambda p: int(p.stem.split('-')[1]))
        if not checkpoints:
            continue
        checkpoint = checkpoints[-1]
        state = torch.load(checkpoint, map_location='cuda', weights_only=False)
        model = Policy(state['model']['body.0.weight'].shape[1]).cuda()
        model.load_state_dict(state['model']); model.eval()
        for mode in ('sampled', 'greedy'):
            result = evaluate(env, model, mode=mode, seed=args.seed)
            result.update(policy=folder.name, checkpoint=str(checkpoint))
            rows.append(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2, allow_nan=False) + '\n')
    print(json.dumps(rows, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
