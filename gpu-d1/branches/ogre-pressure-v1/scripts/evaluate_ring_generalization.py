#!/usr/bin/env python3
"""Matched per-layout evaluation for the corrected ring comparison."""
import argparse
import json
import pathlib
import sys

import torch

from learn_env_ring_multi import Env
from train_clear import Policy, evaluate


def load_policy(path, obs):
    model = Policy(obs).cuda()
    state = torch.load(path, map_location='cuda', weights_only=False)
    model.load_state_dict(state['model'])
    model.eval()
    return model


def panel(env_root, ids, episodes, policies, mode, seed):
    rows = []
    env = Env(episodes, 40, seed=seed, corpus=env_root, map_filter=ids[0])
    for map_id in ids:
        # Reuse the resident flattened corpus. Reconstructing Env would copy
        # gigabytes of map tables for every layout.
        env.tables.map_filter = map_id
        env.reset(seed)
        row = {'map_id': map_id, 'seed': env.metadata[map_id]['seed']}
        for name, model in policies.items():
            result = evaluate(env, model, mode, seed=seed)
            row[name] = {k: result[k] for k in
                         ('clear_rate', 'enemies_killed', 'death_rate', 'timeout_rate', 'mean_length', 'mean_return')}
        rows.append(row)
    del env
    torch.cuda.empty_cache()
    return rows


def summarize(rows, name):
    keys = ('clear_rate', 'enemies_killed', 'death_rate', 'timeout_rate', 'mean_length', 'mean_return')
    return {name: {k: sum(r[name][k] for r in rows) / len(rows) for k in keys}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--single-checkpoint', type=pathlib.Path, required=True)
    ap.add_argument('--multi-checkpoint', type=pathlib.Path, required=True)
    ap.add_argument('--corpus', type=pathlib.Path, default=pathlib.Path('gpu-d1/fixtures/d1-corpus-388'))
    ap.add_argument('--episodes-per-map', type=int, default=64)
    ap.add_argument('--output', type=pathlib.Path, required=True)
    args = ap.parse_args()
    torch.set_num_threads(1)
    train_root = args.corpus / 'train'
    validation_root = args.corpus / 'validation'
    probe = Env(1, 40, seed=1, corpus=train_root, map_filter=0)
    policies = {
        'single': load_policy(args.single_checkpoint, probe.obs.shape[1]),
        'multi': load_policy(args.multi_checkpoint, probe.obs.shape[1]),
    }
    del probe
    torch.cuda.empty_cache()
    train_ids = [round(i * 255 / 31) for i in range(32)]
    validation_ids = list(range(32))
    result = {
        'settings': {
            'episodes_per_map': args.episodes_per_map,
            'single_checkpoint': str(args.single_checkpoint),
            'multi_checkpoint': str(args.multi_checkpoint),
            'train_panel_ids': train_ids,
            'validation_ids': validation_ids,
            'action_mode': 'sampled',
            'eval_seed': 910000,
        },
        'original_map': panel(train_root, [0], 1024, policies, 'sampled', 910000),
        'train_panel': panel(train_root, train_ids, args.episodes_per_map, policies, 'sampled', 910100),
        'validation': panel(validation_root, validation_ids, args.episodes_per_map, policies, 'sampled', 910200),
    }
    result['summary'] = {}
    for section in ('original_map', 'train_panel', 'validation'):
        if section == 'original_map':
            result['summary'][section] = {k: result[section][0][k] for k in ('single', 'multi')}
        else:
            result['summary'][section] = {}
            for name in ('single', 'multi'):
                result['summary'][section].update(summarize(result[section], name))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()
