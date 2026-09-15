#!/usr/bin/env python3
"""Trajectory diagnostics for the sleep-only policy checkpoint."""
import argparse
import collections
import json
import pathlib
import numpy as np
import torch
from train_clear import Policy
from learn_env_sleep import Env


def summarize(values):
    values = np.asarray(values, dtype=np.float64)
    if not len(values):
        return None
    return {
        'mean': float(values.mean()),
        'p10': float(np.percentile(values, 10)),
        'p50': float(np.percentile(values, 50)),
        'p90': float(np.percentile(values, 90)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--checkpoint', type=pathlib.Path, required=True)
    ap.add_argument('--output', type=pathlib.Path, required=True)
    ap.add_argument('--episodes', type=int, default=2048)
    ap.add_argument('--seed', type=int, default=1300000)
    ap.add_argument('--mode', choices=('sampled', 'greedy'), default='sampled')
    args = ap.parse_args()
    torch.set_num_threads(1)
    env = Env(args.episodes, 8, seed=args.seed)
    state = torch.load(args.checkpoint, map_location='cuda', weights_only=False)
    # Infer the input width so this diagnostic also handles observation
    # ablations such as the local seen-history channel.
    model = Policy(state['model']['body.0.weight'].shape[1]).cuda()
    model.load_state_dict(state['model']); model.eval()

    n, limit = args.episodes, env.limit
    active = np.ones(n, dtype=bool)
    terminal = np.full(n, '', dtype=object)
    terminal_step = np.full(n, -1, dtype=np.int32)
    final_kills = np.zeros(n, dtype=np.int32)
    final_hp = np.zeros(n, dtype=np.float32)
    steps = np.zeros(n, dtype=np.int32)
    moves = np.zeros(n, dtype=np.int32)
    attacks = np.zeros(n, dtype=np.int32)
    waits = np.zeros(n, dtype=np.int32)
    near_steps = np.zeros(n, dtype=np.int32)
    min_nearest = np.full(n, 999, dtype=np.int32)
    initial_nearest = np.full(n, 999, dtype=np.int32)
    target_switches = np.zeros(n, dtype=np.int32)
    previous_target = np.full(n, -1, dtype=np.int32)
    wake_seen = np.zeros((n, 8), dtype=bool)
    visited = [set() for _ in range(n)]
    rings = [collections.deque(maxlen=100) for _ in range(n)]
    representatives = {'clear': [], 'death': [], 'timeout': []}

    with torch.random.fork_rng(devices=[env.device.index]):
        torch.manual_seed(args.seed)
        for t in range(limit):
            active_before = active.copy()
            enemy = env.obs[:, 162:202].detach().cpu().numpy().reshape(n, 8, 5)
            player = env.obs[:, 204:206].detach().cpu().numpy()
            px = np.rint(player[:, 0] * 80).astype(np.int32)
            py = np.rint(player[:, 1] * 70).astype(np.int32)
            relx = enemy[:, :, 0] * 80
            rely = enemy[:, :, 1] * 70
            distances = np.maximum(np.abs(relx), np.abs(rely)).astype(np.int32)
            alive = enemy[:, :, 4] > 0.5
            masked_distances = np.where(alive, distances, 999)
            target = masked_distances.argmin(axis=1).astype(np.int32)
            nearest = masked_distances[np.arange(n), target]
            near = alive & (distances <= 6)
            wake_seen |= near
            for j in np.flatnonzero(active_before):
                pos = (int(px[j]), int(py[j]))
                visited[j].add(pos)
                steps[j] += 1
                near_steps[j] += int(near[j].any())
                min_nearest[j] = min(min_nearest[j], int(nearest[j]))
                if t == 0:
                    initial_nearest[j] = int(nearest[j])
                if previous_target[j] >= 0 and target[j] != previous_target[j]:
                    target_switches[j] += 1
                previous_target[j] = target[j]

            if args.mode == 'greedy':
                dist, _ = model(env.obs, env.mask)
                actions = dist.probs.argmax(-1)
            else:
                dist, _ = model(env.obs, env.mask)
                actions = dist.sample()
            actions_np = actions.detach().cpu().numpy().astype(np.int32)
            _, out = env.step(actions)
            out_np = out.detach().cpu().numpy()
            ended = active_before & (out_np[:, 1] > 0.5)
            next_player = env.obs[:, 204:206].detach().cpu().numpy()
            next_px = np.rint(next_player[:, 0] * 80).astype(np.int32)
            next_py = np.rint(next_player[:, 1] * 70).astype(np.int32)
            moved = active_before & ~ended & ((next_px != px) | (next_py != py))
            attack = active_before & (actions_np < 8) & ~moved
            for j in np.flatnonzero(active_before):
                row = [
                    int(t), int(px[j]), int(py[j]), int(actions_np[j]),
                    int(out_np[j, 3]), int(alive[j].sum()), int(nearest[j]), int(near[j].sum()),
                    int(moved[j]), int(attack[j]), int(actions_np[j] == 8),
                    float(enemy[j, :, 2].sum()), float(out_np[j, 4]),
                    int(ended[j]),
                ]
                rings[j].append(row)
                moves[j] += int(moved[j]); attacks[j] += int(attack[j]); waits[j] += int(actions_np[j] == 8)

            for j in np.flatnonzero(ended):
                kind = 'clear' if out_np[j, 2] > 0.5 else ('death' if out_np[j, 6] > 0.5 else 'timeout')
                terminal[j] = kind; terminal_step[j] = t
                final_kills[j] = int(out_np[j, 3]); final_hp[j] = out_np[j, 4]
                if len(representatives[kind]) < 6:
                    representatives[kind].append({
                        'episode': int(j), 'terminal_step': int(t), 'kills': int(out_np[j, 3]),
                        'hp': float(out_np[j, 4]), 'unique_positions': len(visited[j]),
                        'steps_near_enemy': int(near_steps[j]),
                        'woke_enemy_slots': np.flatnonzero(wake_seen[j]).tolist(),
                        'last_100_turns': list(rings[j]),
                    })
            active &= ~ended
            if not active.any():
                break

    if active.any():
        raise RuntimeError(f'{int(active.sum())} episodes did not terminate')

    summaries = {}
    for kind in ('clear', 'death', 'timeout'):
        idx = terminal == kind
        if not idx.any():
            summaries[kind] = {'episodes': 0}
            continue
        summaries[kind] = {
            'episodes': int(idx.sum()),
            'fraction': float(idx.mean()),
            'kills': summarize(final_kills[idx]),
            'hp_at_end': summarize(final_hp[idx]),
            'episode_steps': summarize(steps[idx]),
            'unique_positions': summarize([len(visited[j]) for j in np.flatnonzero(idx)]),
            'move_fraction': float(moves[idx].sum() / max(1, steps[idx].sum())),
            'attack_fraction': float(attacks[idx].sum() / max(1, steps[idx].sum())),
            'wait_fraction': float(waits[idx].sum() / max(1, steps[idx].sum())),
            'near_enemy_fraction': float(near_steps[idx].sum() / max(1, steps[idx].sum())),
            'initial_nearest': summarize(initial_nearest[idx]),
            'minimum_nearest': summarize(min_nearest[idx]),
            'target_switches': summarize(target_switches[idx]),
            'woke_enemy_count': summarize(wake_seen[idx].sum(axis=1)),
        }

    result = {
        'checkpoint': str(args.checkpoint), 'mode': args.mode, 'episodes': n,
        'seed': args.seed, 'limit': limit, 'summaries': summaries,
        'representatives': representatives,
        'action_encoding': ['north', 'east', 'south', 'west', 'northeast', 'southeast', 'southwest', 'northwest', 'wait'],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
