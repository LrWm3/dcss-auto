#!/usr/bin/env python3
"""Evaluate a saved v2 policy against controls or held-out stat regimes."""
import argparse, json, pathlib
import torch
from train_v2 import Policy, evaluate
from learn_env_v2 import EnvV2, ROOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--checkpoint', type=pathlib.Path, required=True)
    ap.add_argument('--corpus', type=pathlib.Path, default=ROOT/'fixtures/v2-test')
    ap.add_argument('--episodes', type=int, default=2048)
    ap.add_argument('--enemies', type=int, default=4)
    ap.add_argument('--limit', type=int, default=512)
    ap.add_argument('--sleep-radius', type=int, default=6)
    ap.add_argument('--stat-mode', type=int, default=1)
    ap.add_argument('--player-mode', type=int, default=1)
    ap.add_argument('--seed', type=int, default=900000)
    args = ap.parse_args()
    torch.set_num_threads(1)
    env = EnvV2(args.episodes, args.enemies, seed=args.seed, limit=args.limit,
                corpus=args.corpus, sleep_radius=args.sleep_radius,
                stat_mode=args.stat_mode, player_mode=args.player_mode)
    model = Policy().cuda()
    state = torch.load(args.checkpoint, map_location='cuda', weights_only=False)
    model.load_state_dict(state['model']); model.eval()
    result = {
        'checkpoint': str(args.checkpoint), 'stat_mode': args.stat_mode,
        'player_mode': args.player_mode,
        'greedy': evaluate(env, model, 'greedy', args.seed),
        'sampled': evaluate(env, model, 'sampled', args.seed),
    }
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
