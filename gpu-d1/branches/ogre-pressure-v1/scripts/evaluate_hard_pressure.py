"""Evaluation-only close, awake ogre suite. No fitting or policy-selected scenarios.

Run with the shared gpu-d1/.venv/bin/python. Retains compact metrics, not weights.
Geometry is disjoint from the original pressure train/validation set. Four
placement/energy cases share each geometry; these are not independent layouts.
"""
import argparse
import collections
import hashlib
import json
import pathlib
import random
import subprocess
import time

import numpy as np
import torch
from torch import nn
from torch.distributions import Categorical
from generate_pressure import W, H, N, DELTAS, canonical, neighbors, write_map
from learn_env_ring_multi import Env

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHARED = ROOT.parents[1]


def generate(destination):
    destination.mkdir(parents=True, exist_ok=True)
    excluded = {m['canonical_geometry_sha256'] for m in
                json.loads((ROOT/'fixtures/pressure/manifest.json').read_text())['scenarios']}
    rows = []
    # Freeze all cases before evaluating policies. Do not discard difficult cases.
    for geometry, (width, height, thickness) in enumerate(
            (w, h, t) for t in (2, 3) for w in (12, 14) for h in (9, 11, 13)):
        r = random.Random(1200000 + geometry)
        ox, oy = r.randint(8, 50), r.randint(8, 42)
        floor = np.zeros((H, W), dtype=np.uint8)
        floor[oy:oy+height, ox:ox+width] = 1
        floor[oy+thickness:oy+height-thickness, ox+thickness:ox+width-thickness] = 0
        flip_x, flip_y = bool(r.randrange(2)), bool(r.randrange(2))
        def position(x, y):
            x, y = ox+x, oy+y
            return (H-1-y if flip_y else y)*W + (W-1-x if flip_x else x)
        if flip_x:
            floor = floor[:, ::-1]
        if flip_y:
            floor = floor[::-1]
        floor = floor.copy().reshape(-1)
        sha = hashlib.sha256(canonical(floor)).hexdigest()
        assert sha not in excluded
        excluded.add(sha)
        for distance in (3, 5):
            for energy in (70, 75):
                p, q, s = position(1, 1), position(1+distance, 1), position(width-2, 1)
                safe = floor.copy()
                for z in np.flatnonzero(safe):
                    if max(abs(int(z)%W-q%W), abs(int(z)//W-q//W)) <= 2:
                        safe[z] = 0
                seen, queue = {p}, collections.deque([p])
                while queue:
                    for z in neighbors(queue.popleft(), safe):
                        if z not in seen:
                            seen.add(z); queue.append(z)
                assert s in seen
                seed = 1200000 + len(rows)
                meta = dict(seed=seed, player=p, ogre=q, monster=s, awake=1, energy=energy,
                            family='close_awake_loop', geometry_id=geometry,
                            initial_distance=distance, corridor_width=thickness,
                            canonical_geometry_sha256=sha, static_safe_path=True,
                            split='diagnostic_test', label='ogre_pressure',
                            scenario_id=f'hard-{len(rows):03d}')
                path = destination/f'map-{seed}.bin'
                write_map(path, floor, meta)
                chars = np.where(floor.reshape(H, W), '.', '#')
                for z, char in ((p, '@'), (q, 'q'), (s, 's')):
                    chars[z//W, z%W] = char
                ys, xs = np.nonzero(floor.reshape(H, W))
                path.with_suffix('.txt').write_text('\n'.join(''.join(row) for row in
                    chars[ys.min():ys.max()+1, xs.min():xs.max()+1])+'\n')
                rows.append(meta)
    (destination/'manifest.json').write_text(json.dumps(rows, indent=2)+'\n')
    return rows


class Policy(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(741, width), nn.Tanh(), nn.Linear(width, width), nn.Tanh())
        self.actor, self.critic = nn.Linear(width, 9), nn.Linear(width, 1)

    def forward(self, obs, mask):
        return Categorical(logits=self.actor(self.body(obs)).masked_fill(mask == 0, -1e9))


def oracle(obs, floor):
    # Full-map feasibility witness, never supplied as demonstrations or rewards.
    px, py = round(float(obs[364])*W), round(float(obs[365])*H)
    p = py*W+px
    target = p+round(float(obs[162])*W)+W*round(float(obs[163])*H)
    q = p+round(float(obs[282])*W)+W*round(float(obs[283])*H)
    def distance(z):
        return max(abs(z%W-q%W), abs(z//W-q//W))
    queue, first = collections.deque([p]), {p: 8}
    while queue:
        x = queue.popleft()
        if x == target:
            return first[x]
        for d, (dx, dy) in enumerate(DELTAS):
            xx, yy = x%W+dx, x//W+dy
            z = yy*W+xx
            if 0 <= xx < W and 0 <= yy < H and floor[z] and z not in first and distance(z)>2:
                first[z] = d if x == p else first[x]; queue.append(z)
    choices = []
    for d, (dx, dy) in enumerate(DELTAS):
        xx, yy = px+dx, py+dy
        if 0 <= xx < W and 0 <= yy < H and floor[yy*W+xx]:
            choices.append((distance(yy*W+xx), d))
    return max(choices)[1] if choices else 8


@torch.no_grad()
def evaluate(corpus, library, model, episodes, seed, oracle_mode=False):
    count = len(list(corpus.glob('map-*.bin')))
    device = 'cpu' if oracle_mode else 'cuda'
    env = Env(batch=count*episodes, enemies=26, seed=seed, device=device, corpus=corpus,
              map_filter=-2, pressure_only=True, library_path=library)
    active = torch.ones(env.batch, dtype=torch.bool, device=device)
    terminal = torch.zeros_like(env.out)
    near = torch.zeros_like(active); disengaged = torch.zeros_like(active)
    near_turns = torch.zeros(env.batch, device=device)
    floor = env.arrays[0].cpu().numpy().reshape(count, N) if oracle_mode else None
    torch.manual_seed(seed)
    start = time.monotonic()
    for _ in range(1024):
        if oracle_mode:
            action = torch.tensor([oracle(env.obs[i], floor[i%count]) if active[i] else 8
                                   for i in range(env.batch)])
        else:
            action = model(env.obs, env.mask).sample()
        _, out = env.step(action, active=active)
        near |= active & (out[:, 17]>0)
        near_turns += active*out[:, 17]
        ended = active & (out[:, 1]>0)
        # Post-transition obs resets on terminal, so never use it for ended worlds.
        distance = (env.obs[:, 282:284]*env.obs.new_tensor([W, H])).abs().amax(1)
        disengaged |= active & ~ended & near & (distance >= 4.999) & (out[:, 9]==0) & (out[:, 13]>0)
        terminal[ended] = out[ended]
        active &= ~ended
        if not active.any():
            break
    assert not active.any()
    t = terminal.cpu(); near = near.cpu(); disengaged = disengaged.cpu(); near_turns = near_turns.cpu()
    def metrics(ids):
        a = t[ids]; exposed = near[ids]
        return dict(episodes=len(a), clear_rate=float(a[:, 2].mean()), death_rate=float(a[:, 6].mean()),
                    timeout_rate=float(a[:, 7].mean()), ogre_death_rate=float(a[:, 14].mean()),
                    ogre_damage=float(a[:, 9].mean()), ogre_hit_rate=float((a[:, 9]>0).float().mean()),
                    damage_free_clear_rate=float(((a[:, 2]>0)&(a[:, 9]==0)).float().mean()),
                    clear_ogre_alive_rate=float(((a[:, 2]>0)&(a[:, 13]>0)).float().mean()),
                    ogres_killed=float(a[:, 8].mean()), turns=float(a[:, 5].mean()),
                    near_rate=float(exposed.float().mean()), near_turns=float(near_turns[ids].mean()),
                    damage_free_disengage_rate=float(disengaged[ids].float().mean()),
                    damage_free_disengage_given_near=float(disengaged[ids][exposed].float().mean()) if exposed.any() else None)
    per_map = [dict(scenario_id=m.get('scenario_id'), geometry_id=m.get('geometry_id'),
                    initial_distance=m.get('initial_distance'), energy=m['energy'],
                    corridor_width=m.get('corridor_width'), **metrics(torch.arange(i, env.batch, count)))
               for i, m in enumerate(env.metadata)]
    return dict(metrics=metrics(torch.arange(env.batch)), per_map=per_map,
                evaluation_seconds=time.monotonic()-start, seed=seed)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=pathlib.Path, default=SHARED/'results/hard-ogre-pressure')
    ap.add_argument('--episodes-per-scenario', type=int, default=32)
    args = ap.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1); torch.backends.cuda.matmul.allow_tf32 = False
    torch.distributions.Distribution.set_default_validate_args(False)
    corpus = ROOT/'fixtures/pressure-hard-test'
    rows = generate(corpus)
    print(f'Frozen {len(rows)} scenarios / 12 novel geometries', flush=True)
    libraries = {}
    for label in (False, True):
        (args.output/'build').mkdir(exist_ok=True)
        lib = args.output/'build'/f'label{int(label)}.so'
        subprocess.run(['nvcc', '-O3', '-std=c++17', '-arch=sm_75', '-ccbin', '/usr/bin/g++-12',
                        '-shared', '-Xcompiler', '-fPIC', '-DLEARN_ENEMIES=40', '-DMULTI_MAP',
                        '-DSLEEP_ON', '-DEXPLORE_REWARD', '-DMARK_WALLS', '-DEXPLORE_MILLI=2',
                        '-DFRONTIER_RING_MEMORY_WALLS_OBS', '-DKNOWN_FRONTIER', '-DFRONTIER_ROUTE_CUE_OBS',
                        '-DOGRE_COUNT=2', '-DOGRE_FEATURES=0', f'-DOPTIONAL_LABEL_OBS={int(label)}',
                        str(ROOT/'src/learn.cu'), '-o', str(lib)], check=True)
        libraries[label] = lib.resolve()
    # Several combat RNG seeds per scenario; a failed oracle is inconclusive.
    result = dict(protocol=dict(scenarios=len(rows), geometries=12, episodes_per_scenario=args.episodes_per_scenario,
                  training=False, source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in (pathlib.Path(__file__), ROOT/'src/learn.cu', ROOT/'src/sim.h')},
                  scenario_manifest_sha256=hashlib.sha256((corpus/'manifest.json').read_bytes()).hexdigest(),
                  disengage_definition='After awake-ogre distance <=3 exposure, reach distance >=5 while alive, ogre alive, and no ogre damage yet; terminal-reset observations excluded.'),
                  oracle=evaluate(corpus, libraries[True], None, 4, 920000, True), policies={})
    print('Oracle', result['oracle']['metrics'], flush=True)
    policies = {
        'ordinary_50m_label': 'ogre-pressure-screen-50m/runs/ordinary_only-seed0',
        'pressure10_50m_label': 'ogre-pressure-screen-50m/runs/pressure10-seed0',
        'ordinary_50m_no_label': 'ogre2-no-optional-label-50m/runs/ogre2_no_optional_label-seed0',
        'ordinary_150m_label': 'ogre2-baseline-150m-fast/runs/ogre2_base-seed0',
    }
    for name, relative in policies.items():
        checkpoint = SHARED/'learning-runs'/relative/'latest.pt'
        saved = torch.load(checkpoint, map_location='cpu', weights_only=False)
        job = saved['job']; label = job.get('optional_label', not job.get('no_optional_label', False))
        assert job['ogre_features']==0 and job.get('frames', 1)==1 and not job['no_xy'] and not job['no_ring']
        model = Policy(job['width']).cuda(); model.load_state_dict(saved['model']); model.eval()
        item = dict(checkpoint=str(checkpoint.relative_to(SHARED)), decisions=saved['decisions'], optional_label=label,
                    checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                    hard=evaluate(corpus, libraries[label], model, args.episodes_per_scenario, 900000),
                    original=evaluate(ROOT/'fixtures/pressure/validation', libraries[label], model, 32, 900000))
        result['policies'][name] = item
        (args.output/'results.json').write_text(json.dumps(result, indent=2)+'\n')
        print(name, 'hard', item['hard']['metrics'], 'original', item['original']['metrics']['clear_rate'], flush=True)
    class Control:
        def __init__(self, chase):
            self.chase = chase

        def __call__(self, obs, mask):
            logits = torch.zeros_like(mask)
            if self.chase:
                # Follow the required monster's relative position, with no ogre input.
                target = obs[:, 162:164]*obs.new_tensor([W, H])
                moves = obs.new_tensor([*DELTAS, (0, 0)])
                distance = (target[:, None, :]-moves[None, :, :]).abs().amax(-1)
                best = distance.masked_fill(mask == 0, float('inf')).amin(-1, keepdim=True)
                logits = logits.masked_fill(distance > best+1e-5, -1e9)
            return Categorical(logits=logits.masked_fill(mask == 0, -1e9))
    result['controls'] = {name: evaluate(corpus, libraries[False], Control(chase),
                                        args.episodes_per_scenario, 900000)
                          for name, chase in [('random_legal', False), ('required_monster_chase', True)]}
    for name, item in result['controls'].items():
        print(name, item['metrics'], flush=True)
    (args.output/'results.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
