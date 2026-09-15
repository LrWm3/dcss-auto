#!/usr/bin/env python3
"""Evaluate saved frontier policies with temperature-scaled actions and navigation diagnostics."""
import argparse
import json
import pathlib
import time

import numpy as np
import torch
from torch.distributions import Categorical, Distribution

from ablation_storage import Store
from learn_env_ring_multi import Env
from run_ring_ablations import ROOT, GIB, digest
from train_clear import Policy


@torch.no_grad()
def evaluate(env, model, temperature, seed):
    torch.cuda.synchronize()
    start = time.perf_counter()
    env.reset(seed)
    torch.manual_seed(seed)
    n = env.batch
    active = np.ones(n, bool)
    terminal = np.zeros((n, 8))
    visited = np.zeros((n, 5600), bool)
    seen = np.zeros_like(visited)
    positions = np.full((32, n), -1, np.int32)
    contacts = np.zeros((32, n), bool)
    loops = np.zeros(n)
    reversals = np.zeros(n)
    steps = np.zeros(n)
    ids = np.arange(n)
    dx, dy = np.meshgrid(np.arange(-4, 5), np.arange(-4, 5))
    for t in range(1024):
        obs = env.obs.cpu().numpy()
        x = np.rint(obs[:, 364]*80).astype(int)
        y = np.rint(obs[:, 365]*70).astype(int)
        pos = y*80+x
        visited[ids[active], pos[active]] = True
        xx, yy = x[:, None]+dx.ravel(), y[:, None]+dy.ravel()
        valid = (xx >= 0) & (xx < 80) & (yy >= 0) & (yy < 70)
        exposed = valid & (obs[:, :81] > .5) & active[:, None]
        rows, cols = np.nonzero(exposed)
        seen[rows, (yy*80+xx)[rows, cols]] = True
        enemies = obs[:, 162:362].reshape(n, 40, 5)
        near = ((enemies[:, :, 4] > .5) &
                (np.abs(enemies[:, :, 0]*80) < 1.1) &
                (np.abs(enemies[:, :, 1]*70) < 1.1)).any(axis=1)
        if t >= 2:
            reversals += active & ~near & (pos == positions[(t-2) % 32]) & (pos != positions[(t-1) % 32])
        positions[t % 32] = pos
        contacts[t % 32] = near
        if t >= 31:
            ordered = np.sort(positions, axis=0)
            distinct = 1+(ordered[1:] != ordered[:-1]).sum(axis=0)
            loops += active & (distinct <= 2) & ~contacts.any(axis=0)
        steps += active
        dist, _ = model(env.obs, env.mask)
        action = dist.logits.argmax(-1) if temperature == 0 else Categorical(logits=dist.logits/temperature).sample()
        _, out = env.step(action)
        out = out.cpu().numpy()
        ended = active & (out[:, 1] > .5)
        terminal[ended] = out[ended]
        active &= ~ended
    assert not active.any()
    torch.cuda.synchronize()
    seconds = time.perf_counter()-start
    cells = np.array([m['cells'] for m in env.metadata])[ids % len(env.metadata)]
    def metrics(select):
        count = int(select.sum())
        if not count:
            return dict(episodes=0)
        z = terminal[select]
        return dict(episodes=count, clear_rate=float(z[:, 2].mean()), kills=float(z[:, 3].mean()),
                    death_rate=float(z[:, 6].mean()), timeout_rate=float(z[:, 7].mean()),
                    turns=float(z[:, 5].mean()), unique_positions=float(visited[select].sum(1).mean()),
                    seen_floor_fraction=float((seen.sum(1)/cells)[select].mean()),
                    quiet_stall_window_fraction=float((loops/steps)[select].mean()),
                    quiet_reversal_fraction=float((reversals/steps)[select].mean()))
    return dict(temperature=temperature, evaluation_seconds=seconds,
                overall=metrics(np.ones(n, bool)),
                by_outcome={name: metrics(terminal[:, col] > .5)
                            for name, col in [('clear', 2), ('death', 6), ('timeout', 7)]},
                by_map={str(m['seed']): metrics(ids % len(env.metadata) == i)
                        for i, m in enumerate(env.metadata)})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=pathlib.Path, default=ROOT/'results/frontier-randomness')
    ap.add_argument('--temperatures', default='0,0.25,0.5,1,1.5,2')
    ap.add_argument('--episodes-per-map', type=int, default=32)
    args = ap.parse_args()
    temperatures = [float(x) for x in args.temperatures.split(',')]
    assert all(np.isfinite(x) and x >= 0 for x in temperatures)
    assert args.episodes_per_map > 0
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    Distribution.set_default_validate_args(False)
    args.output.mkdir(parents=True, exist_ok=True)
    store = Store(args.output, GIB, 5*GIB)
    settings = dict(temperatures=temperatures, episodes_per_map=args.episodes_per_map,
                    evaluation_seed=910777, source_sha256=digest(pathlib.Path(__file__)),
                    coverage='Floor tiles visible in pre-action 9x9 observations; terminal observation excluded because of auto-reset.',
                    stall='Fraction of turns ending a 32-position window with at most two distinct positions and no adjacent live enemy throughout.',
                    timing='Evaluation includes diagnostics, excludes model/map loading; no training performed.')
    path = store.root/'settings.json'
    if path.exists() and json.loads(path.read_text()) != settings:
        raise ValueError('Different settings: choose a new output directory')
    store.json('settings.json', settings)
    started = time.perf_counter()
    for seed in range(3):
        suite = ROOT/'learning-runs'/('ring-ablation-suite' if seed == 0 else 'ring-frontier-replication')
        folder = suite/'runs'/f'known_frontier-seed{seed}'
        lib = suite/'build/ring-reward2-frontier1.so'
        assert digest(lib) == lib.with_suffix('.sha256').read_text().strip()
        config = json.loads((folder/'config.json').read_text())
        checkpoint = folder/'best.pt'
        saved = torch.load(checkpoint, map_location='cpu', weights_only=False)
        env = Env(args.episodes_per_map*32, 40, corpus=ROOT/'fixtures/d1-corpus-388/validation',
                  map_limit=32, map_filter=-2, library_path=lib)
        assert env.metadata == config['validation_maps']
        model = Policy(env.obs.shape[1]).cuda()
        model.load_state_dict(saved['model'])
        model.eval()
        for temperature in temperatures:
            row = evaluate(env, model, temperature, settings['evaluation_seed'])
            row.update(seed=seed, checkpoint=str(checkpoint), checkpoint_sha256=digest(checkpoint),
                       checkpoint_decisions=saved['decisions'], library_sha256=digest(lib))
            store.json(f'seed{seed}-temperature{temperature:g}.json', row)
            print(json.dumps(dict(seed=seed, temperature=temperature,
                                  evaluation_seconds=round(row['evaluation_seconds'], 2), **row['overall'])), flush=True)
        del env, model
        torch.cuda.empty_cache()
    rows = [json.loads(p.read_text()) for p in sorted(store.root.glob('seed*-temperature*.json'))]
    store.json('summary.json', dict(rows=rows, elapsed_seconds=time.perf_counter()-started,
                                   evaluation_seconds=sum(r['evaluation_seconds'] for r in rows)))


if __name__ == '__main__':
    main()
