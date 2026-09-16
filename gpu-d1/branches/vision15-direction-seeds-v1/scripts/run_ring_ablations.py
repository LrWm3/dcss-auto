#!/usr/bin/env python3
"""Sequential, resumable ring ablations with bounded checkpoint storage.

Use --dry-run to inspect the plan and --smoke for tiny end-to-end runs.
Training checkpoints contain live worlds and RNG, never the static map tables.
"""
import argparse
import fcntl
import hashlib
import json
import math
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time

from ablation_storage import Store, DiskBudgetError

ROOT = pathlib.Path(__file__).resolve().parents[1]
GIB = 1024**3
MIB = 1024**2
COMMON = dict(frontier=True, route_cue=True, enemies=24, turn_limit=2048,
              terrain_los=1, global_enemies=0, vision_radius=7, ogres=0,
              frontier_travel=False, ogre_features=0, optional_label=False,
              monster_wake_los=True)
VARIANTS = {
    'ordinary': dict(COMMON, clump_mode=0, death_milli=4000, kill_milli=1000, clear_milli=3000, progress_input=2),
    'clumps_third': dict(COMMON, clump_mode=1, death_milli=4000, kill_milli=1000, clear_milli=3000, progress_input=2),
}
DEFAULT = 'ordinary,clumps_third'
SOURCE_FILES = ['src/learn.cu', 'src/sim.h', 'scripts/learn_env.py',
                'scripts/learn_env_v2.py', 'scripts/learn_env_ring_multi.py',
                'scripts/run_ring_ablations.py', 'scripts/ablation_storage.py', 'scripts/frame_stack.py',
                'fixtures/fixture.bin', 'scripts/run_experiment.py']


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(4*MIB), b''):
            h.update(block)
    return h.hexdigest()


def corpus_manifest(root):
    result = {}
    for split in ('train', 'validation'):
        paths = sorted((root / split).glob('map-*.bin'))
        if not paths:
            raise ValueError(f'No compiled maps in {root / split}')
        result[split] = {p.name: digest(p) for p in paths}
    if set(result['train']) & set(result['validation']):
        raise ValueError('Training and validation map IDs overlap')
    return result


def jobs_for(args):
    jobs = []
    names = args.variants.split(',')
    seeds = [int(s) for s in args.seeds.split(',')]
    if len(set(names)) != len(names) or len(set(seeds)) != len(seeds):
        raise ValueError('Duplicate variants or seeds')
    for name in names:
        if name not in VARIANTS:
            raise ValueError(f'Unknown variant {name}; choose from {", ".join(VARIANTS)}')
        for seed in seeds:
            job = dict(name=name, seed=seed, maps=256, width=128, no_xy=False,
                       no_ring=False, frontier=False, route_cue=False, explore_milli=2, gamma=.99,
                       awake=False, frames=1, death_milli=1000, performance=args.performance,
                       steps=args.baseline_steps if name == 'baseline' else args.steps,
                       batch=512, horizon=64, eval_per_map=args.eval_per_map,
                       validation_maps=32, checkpoint_every=args.checkpoint_every,
                       lr=.0003, epochs=4, minibatch=4096, entropy=.01, gae_lambda=.95)
            job.update(VARIANTS[name])
            if args.smoke:
                job.update(maps=min(job['maps'], 2), steps=512, batch=8, horizon=16,
                           eval_per_map=2, validation_maps=2, checkpoint_every=256,
                           epochs=1, minibatch=128)
            if min(job['steps'], job['checkpoint_every'], job['eval_per_map']) <= 0:
                raise ValueError('Steps, checkpoint interval and evaluation counts must be positive')
            job['id'] = f'{name}-seed{seed}'
            jobs.append(job)
    return jobs


def library_key(job):
    key = f'progress{job["progress_input"]}-kill{job["kill_milli"]}-clear{job["clear_milli"]}-ring-reward{job["explore_milli"]}-frontier{int(job["frontier"])}-route{int(job.get("route_cue", False))}'
    if job.get('awake'):
        key += '-awake'
    if job.get('death_milli', 1000) != 1000:
        key += f'-death{job["death_milli"]}'
    if job.get('clear_per_enemy_milli', 0):
        key += f'-clear-per-enemy{job["clear_per_enemy_milli"]}'
    if 'heal_charges' in job:
        key += f'-heal{job["heal_charges"]}'
    if job.get('performance') == 'fast':
        key += '-fast'
    return key + f'-clump{job.get("clump_mode",0)}-los{job["terrain_los"]}-global{job["global_enemies"]}-wake{int(job["monster_wake_los"])}-ogres{job["ogres"]}-t2048-v15-travel{int(job["frontier_travel"])}'


def timing_fields(decisions, seconds):
    return dict(train_seconds=round(seconds, 3),
                decisions_per_train_second=round(decisions / seconds, 1) if seconds > 0 else None)


def report_completed(result):
    print(json.dumps(dict(job=result['job']['id'], status='complete',
                          decisions=result['decisions'],
                          **timing_fields(result['decisions'], result['train_seconds']))), flush=True)


def build(store, job):
    relative = pathlib.Path('build') / (library_key(job) + '.so')
    target = store.target(relative)
    if target.exists():
        expected = target.with_suffix('.sha256')
        if not expected.exists() or expected.read_text().strip() != digest(target):
            raise ValueError(f'Corrupt/unverified compiled library: {target}')
        return target
    # Reserve scratch + destination before invoking the compiler. Compilation
    # is sequential and temporary intermediates are removed on exit.
    store.ensure(128*MIB)
    target.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='compile-', dir=target.parent) as tmp:
        output = pathlib.Path(tmp) / 'library.so'
        flags = [f'-DCLUMP_MODE={job.get("clump_mode",0)}', f'-DPROGRESS_INPUT={job["progress_input"]}', f'-DFRONTIER_TRAVEL={int(job["frontier_travel"])}', f'-DOGRE_COUNT={job["ogres"]}', f'-DMONSTER_WAKE_LOS={int(job["monster_wake_los"])}', f'-DTERRAIN_LOS={job["terrain_los"]}', f'-DGLOBAL_ENEMIES={job["global_enemies"]}', '-DLEARN_ENEMIES=40', '-DMULTI_MAP', '-DSLEEP_ON', '-DEXPLORE_REWARD',
                 '-DMARK_WALLS', f'-DEXPLORE_MILLI={job["explore_milli"]}']
        flags += (['-DFRONTIER_RING_MEMORY_WALLS_OBS', '-DKNOWN_FRONTIER'] if job['frontier']
                  else ['-DFRONTIER_RING_WALLS_OBS'])
        if job.get('route_cue'):
            flags.append('-DFRONTIER_ROUTE_CUE_OBS')
            if job.get('performance') == 'fast':
                flags += ['-DFAST_FRONTIER', '-DLEARN_BLOCK_SIZE=4']
            else:
                flags.append('-DREFERENCE_PERFORMANCE')
        if job.get('awake'):
            flags.append('-DMONSTER_AWAKE_OBS')
        flags += [f'-DKILL_MILLI={job["kill_milli"]}', f'-DCLEAR_MILLI={job["clear_milli"]}']
        flags.append(f'-DDEATH_MILLI={job.get("death_milli", 1000)}')
        flags.append(f'-DCLEAR_PER_ENEMY_MILLI={job.get("clear_per_enemy_milli", 0)}')
        if 'heal_charges' in job:
            flags.append(f'-DHEAL_CHARGES={job["heal_charges"]}')
        command = ['nvcc', '-O3', '-std=c++17', '-arch=sm_75', '-ccbin', '/usr/bin/g++-12',
                   '-shared', '-Xcompiler', '-fPIC', *flags, str(ROOT/'src/learn.cu'), '-o', str(output)]
        print('Building', library_key(job), flush=True)
        proc = subprocess.Popen(command, env=os.environ | {'TMPDIR': tmp})
        try:
            while proc.poll() is None:
                store.ensure(0)
                time.sleep(.2)
            if proc.returncode:
                raise RuntimeError(f'Compiler exited {proc.returncode}')
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait()
        size = output.stat().st_size
        if size > 32*MIB:
            raise DiskBudgetError('Compiled library exceeds 32 MiB bound')
        def copy_file(f):
            with output.open('rb') as src:
                for block in iter(lambda: src.read(MIB), b''):
                    f.write(block)
        store.atomic(relative, copy_file, size)
        data = (digest(target) + '\n').encode()
        store.atomic(relative.with_suffix('.sha256'), lambda f: f.write(data), len(data))
    return target


def worker(store, manifest, job):
    # Torch is imported only inside the worker. Each job exits to release GPU
    # allocations and Python map buffers before starting the next variant.
    import torch
    from torch import nn
    from torch.distributions import Categorical, Distribution
    from learn_env_ring_multi import Env
    Distribution.set_default_validate_args(False)
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.manual_seed(job['seed'])
    lib = store.root / 'build' / (library_key(job) + '.so')
    if digest(lib) != lib.with_suffix('.sha256').read_text().strip():
        raise ValueError('Library hash changed')
    corpus = pathlib.Path(manifest['corpus'])
    env = Env(job['batch'], job['enemies'], seed=17+job['seed']*100000, corpus=corpus/'train',
              map_limit=job['maps'], library_path=lib, limit=job['turn_limit'])
    eval_lib = store.root / 'build' / (library_key(dict(job, clump_mode=0)) + '.so')
    ev = Env(job['validation_maps']*job['eval_per_map'], job['enemies'], seed=900000,
             corpus=corpus/'validation', map_limit=job['validation_maps'],
             map_filter=-2, library_path=eval_lib, limit=job['turn_limit'])
    if job.get('frames', 1) > 1:
        from frame_stack import FrameStack
        env, ev = FrameStack(env, job['frames']), FrameStack(ev, job['frames'])

    class Policy(nn.Module):
        def __init__(self):
            super().__init__()
            width = job['width']
            self.body = nn.Sequential(nn.Linear(env.obs.shape[1]-1, width), nn.Tanh(),
                                      nn.Linear(width, width), nn.Tanh())
            self.actor, self.critic = nn.Linear(width, env.mask.shape[1]), nn.Linear(width, 1)
            for layer in self.modules():
                if isinstance(layer, nn.Linear):
                    nn.init.orthogonal_(layer.weight, math.sqrt(2)); nn.init.zeros_(layer.bias)
            nn.init.orthogonal_(self.actor.weight, .01); nn.init.orthogonal_(self.critic.weight, 1)
            # Preserve the original seeded initialization and add a zero-weight
            # feature column, rather than reshuffling every initial parameter.
            first = self.body[0]
            first.weight = nn.Parameter(torch.cat((first.weight.detach(), torch.zeros(width, 1)), dim=1))
            first.in_features += 1

        def forward(self, obs, mask):
            h = self.body(obs)
            return Categorical(logits=self.actor(h).masked_fill(mask == 0, -1e9)), self.critic(h).squeeze(-1)

    def transform(world):
        if job['no_xy']:
            world.obs[:, 652:654] = 0
        if job['no_ring']:
            world.obs[:, 654:718] = 0

    @torch.no_grad()
    def evaluate(mode):
        ev.reset(900000)
        active = torch.ones(ev.batch, dtype=torch.bool, device='cuda')
        terminal = torch.zeros_like(ev.out)
        exposure = torch.zeros((ev.batch,3),device='cuda')
        travel = torch.zeros((ev.batch,7),device='cuda')
        decisions = torch.zeros(ev.batch,device='cuda')
        returns = torch.zeros(ev.batch, device='cuda')
        with torch.random.fork_rng(devices=[0]):
            torch.manual_seed(900000)
            for _ in range(job['turn_limit']):
                transform(ev)
                dist, _ = model(ev.obs, ev.mask)
                action = dist.probs.argmax(-1) if mode == 'greedy' else dist.sample()
                _, out = ev.step(action, active=active if job.get('performance') == 'fast' else None)
                returns += active * out[:, 0]
                exposure += active[:,None] * out[:,21:24]
                travel += active[:,None] * out[:,26:33]
                decisions += active
                ended = active & (out[:, 1] > 0)
                terminal[ended] = out[ended]
                terminal[ended,21:24] = exposure[ended]
                terminal[ended,26:33] = travel[ended]
                terminal[ended,33] = decisions[ended]
                active &= ~ended
        assert not active.any().item()
        terminal, returns = terminal.cpu(), returns.cpu()
        def metrics(t, r):
            result = dict(clear_rate=t[:, 2].mean().item(), kills=t[:, 3].mean().item(),
                        death_rate=t[:, 6].mean().item(), timeout_rate=t[:, 7].mean().item(),
                        turns=t[:, 5].mean().item(), shaped_return=r.mean().item())
            assert torch.equal(t[:,26],t[:,5]), 'Underlying turns must equal episode ticks'
            result.update(policy_decisions=t[:,33].mean().item(),
                underlying_turns=t[:,26].mean().item(),
                turns_per_policy_decision=(t[:,26].sum()/t[:,33].sum()).item(),
                travel_uses=t[:,27].mean().item(), travel_turns=t[:,28].mean().item(),
                travel_arrivals=t[:,29].mean().item(), travel_enemy_interrupts=t[:,30].mean().item(),
                travel_terminal_stops=t[:,31].mean().item(), travel_invalid_or_blocked=t[:,32].mean().item(),
                turns_per_travel_use=(t[:,28].sum()/t[:,27].sum()).item() if t[:,27].sum()>0 else None)
            timeout=t[:,7]>0
            result.update(enemies_encountered=t[:,8].mean().item(),
                          unseen_alive=t[:,9].mean().item(), encountered_alive=t[:,10].mean().item(),
                          floor_coverage=t[:,11].mean().item(), visible_enemies_at_end=t[:,12].mean().item(),
                          floor_tiles_seen=t[:,13].mean().item(),
                          timeout_unseen_alive=t[timeout,9].mean().item() if timeout.any() else None,
                          timeout_encountered_alive=t[timeout,10].mean().item() if timeout.any() else None)
            result.update(ogres_killed=t[:,14].mean().item(), ogre_damage=t[:,15].mean().item(),
                          ogre_actions=t[:,16].mean().item(), ogre_adjacent_turns=t[:,17].mean().item(),
                          awake_ogres_at_end=t[:,18].mean().item(), living_ogres_at_end=t[:,19].mean().item(),
                          ogre_death_rate=t[:,20].mean().item(),
                          ogres_woken=t[:,21].mean().item(),
                          ogre_wake_fraction=t[:,21].mean().item()/job['ogres'] if job['ogres'] else None,
                          any_ogre_woken_rate=(t[:,21]>0).float().mean().item(),
                          awake_ogre_adjacent_turns=t[:,22].mean().item(),
                          awake_ogre_near_turns=t[:,23].mean().item(),
                          awake_ogre_adjacent_turn_fraction=(t[:,22].sum()/t[:,5].sum()).item(),
                          awake_ogre_near_turn_fraction=(t[:,23].sum()/t[:,5].sum()).item(),
                          any_ogre_killed_rate=(t[:,14]>0).float().mean().item(),
                          clear_with_any_ogre_alive_rate=((t[:,2]>0)&(t[:,19]>0)).float().mean().item(),
                          clear_with_all_ogres_alive_rate=((t[:,2]>0)&(t[:,19]==job['ogres'])).float().mean().item(),
                          all_ogres_alive_given_clear=(t[t[:,2]>0,19]==job['ogres']).float().mean().item() if (t[:,2]>0).any() else None)
            result.update(ogres_encountered=t[:,24].mean().item(), visible_ogres_at_end=t[:,25].mean().item())
            if 'heal_charges' in job:
                used = t[:, 8].sum().item()
                dead = t[:, 6] > 0
                result.update(heals_used=t[:, 8].mean().item(),
                              hp_before_heal=t[:, 9].sum().item()/used if used else None,
                              hp_restored_per_heal=t[:, 11].sum().item()/used if used else None,
                              charges_left_at_death=t[dead, 10].mean().item() if dead.any() else None,
                              fraction_deaths_with_charges=(t[dead, 10]>0).float().mean().item() if dead.any() else None)
            return result
        result = metrics(terminal, returns)
        result['maps'] = {str(m['seed']): metrics(terminal[i::job['validation_maps']],
                                                returns[i::job['validation_maps']])
                          for i, m in enumerate(ev.metadata)}
        return result

    model = Policy().cuda()
    opt = torch.optim.Adam(model.parameters(), lr=job['lr'], eps=1e-5)
    folder = pathlib.Path('runs') / job['id']
    latest = store.root / folder / 'latest.pt'
    total = updates = 0
    work_totals = [0]*7
    train_seconds = 0.
    history = []
    best, best_score = None, (-1., -1.)
    if latest.exists():
        saved = torch.load(latest, map_location='cpu', weights_only=False)
        if saved['job'] != job:
            raise ValueError('Resume job does not match checkpoint')
        model.load_state_dict(saved['model']); opt.load_state_dict(saved['optimizer'])
        env.state.copy_(saved['env_state']); env.obs.copy_(saved['env_obs']); env.mask.copy_(saved['env_mask'])
        if job.get('frames', 1) > 1:
            env.restore_raw_observation()
        total, updates = saved['decisions'], saved['updates']
        history, train_seconds = saved['history'], saved['train_seconds']
        work_totals = saved['work_totals']
        best, best_score = saved['best'], tuple(saved['best_score'])
        torch.set_rng_state(saved['torch_rng']); torch.cuda.set_rng_state(saved['cuda_rng'])
        print(f'Resuming {job["id"]} at {total:,} decisions', flush=True)
        del saved
    stop = [False]
    def interrupt(*_):
        stop[0] = True
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)

    def cpu_weights():
        return {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    def persist():
        data = dict(job=job, decisions=total, updates=updates, train_seconds=train_seconds, work_totals=work_totals,
                    model=cpu_weights(), optimizer=opt.state_dict(), history=history,
                    env_state=env.state.cpu(), env_obs=env.obs.cpu(), env_mask=env.mask.cpu(),
                    torch_rng=torch.get_rng_state(), cuda_rng=torch.cuda.get_rng_state(),
                    best=best, best_score=best_score)
        store.atomic(folder/'latest.pt', lambda f: torch.save(data, f), 128*MIB)
        if best is not None:
            store.atomic(folder/'best.pt', lambda f: torch.save(best, f), 16*MIB)
        store.json(folder/'curve.json', history)

    def checkpoint(evaluation=True):
        nonlocal best, best_score
        if evaluation:
            row = dict(decisions=total, train_seconds=train_seconds, train_underlying_turns=work_totals[0], train_travel_uses=work_totals[1], train_travel_turns=work_totals[2],
                       sampled=evaluate('sampled'), greedy=evaluate('greedy'))
            score = (row['sampled']['clear_rate'], row['sampled']['kills'])
            if score > best_score:
                best_score = score
                best = dict(job=job, decisions=total, model=cpu_weights(), score=score)
            history.append(row)
            print(json.dumps(dict(job=job['id'], decisions=total,
                                  **timing_fields(total, train_seconds), underlying_turns=work_totals[0], travel_uses=work_totals[1],
                                  clears=row['sampled']['clear_rate'], kills=row['sampled']['kills'])), flush=True)
        persist()
        if evaluation:
            compact = dict(job=job, decisions=total, train_seconds=train_seconds, model=cpu_weights())
            store.atomic(folder/'snapshots'/f'{total:012d}.pt', lambda f: torch.save(compact, f), 16*MIB)

    store.json(folder/'config.json', dict(job=job, training_maps=env.metadata,
                                         validation_maps=ev.metadata, library_sha256=digest(lib),
                                         observation_size=env.obs.shape[1], torch=torch.__version__,
                                         gpu=torch.cuda.get_device_name(), config=list(env.config)))
    if not latest.exists():
        checkpoint()
    T, B = job['horizon'], job['batch']
    observations = torch.empty((T, B, env.obs.shape[1]), device='cuda')
    masks = torch.empty((T, B, env.mask.shape[1]), device='cuda')
    actions = torch.empty((T, B), dtype=torch.int64, device='cuda')
    oldlp = torch.empty((T, B), device='cuda')
    values, rewards, dones, advantages = [torch.empty_like(oldlp) for _ in range(4)]
    milestones = sorted(set([0, 100_000, 300_000, 1_000_000, 2_000_000, 3_000_000, 5_000_000, 7_500_000, 10_000_000, 15_000_000, 20_000_000, 25_000_000, 30_000_000,
                             100_000_000, 125_000_000, 150_000_000, 200_000_000, job['steps']]))
    milestones = [x for x in milestones if total < x <= job['steps']]
    next_save = (total//job['checkpoint_every']+1)*job['checkpoint_every']
    while total < job['steps'] and not stop[0]:
        # Leave room for an atomic live-world checkpoint throughout training.
        store.ensure(128*MIB)
        torch.cuda.synchronize(); start = time.perf_counter()
        rollout_work=torch.zeros(7,device='cuda',dtype=torch.float64)
        with torch.no_grad():
            for t in range(T):
                transform(env)
                observations[t].copy_(env.obs); masks[t].copy_(env.mask)
                dist, v = model(env.obs, env.mask); action = dist.sample()
                actions[t] = action; oldlp[t] = dist.log_prob(action); values[t] = v
                _, out = env.step(action); rewards[t] = out[:, 0]; dones[t] = out[:, 1]
                rollout_work += out[:,26:33].sum(0)
            transform(env)
            _, nextv = model(env.obs, env.mask)
            gae = torch.zeros(B, device='cuda')
            for t in reversed(range(T)):
                live = 1-dones[t]
                delta = rewards[t]+job['gamma']*nextv*live-values[t]
                gae = delta+job['gamma']*job['gae_lambda']*live*gae
                advantages[t], nextv = gae, values[t]
            returns = (advantages+values).flatten()
            adv = advantages.flatten(); adv = (adv-adv.mean())/(adv.std()+1e-8)
        for _ in range(job['epochs']):
            for inds in torch.randperm(T*B, device='cuda').split(job['minibatch']):
                dist, v = model(observations.flatten(0, 1)[inds], masks.flatten(0, 1)[inds])
                ratio = (dist.log_prob(actions.flatten()[inds])-oldlp.flatten()[inds]).exp()
                pg = -torch.minimum(ratio*adv[inds], ratio.clamp(.8, 1.2)*adv[inds]).mean()
                loss = pg+.25*(v-returns[inds]).square().mean()-job['entropy']*dist.entropy().mean()
                if not torch.isfinite(loss).item():
                    raise RuntimeError('Non-finite PPO loss')
                opt.zero_grad(set_to_none=True); loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), .5); opt.step()
        torch.cuda.synchronize(); train_seconds += time.perf_counter()-start
        total += T*B; updates += 1
        work_totals=[a+int(b) for a,b in zip(work_totals,rollout_work.cpu().tolist())]
        do_eval = bool(milestones and total >= milestones[0])
        if do_eval:
            milestones = [x for x in milestones if x > total]
        if do_eval or total >= next_save or stop[0]:
            checkpoint(evaluation=do_eval)
            next_save = (total//job['checkpoint_every']+1)*job['checkpoint_every']
    if stop[0]:
        persist()
        print('Stopped at an update boundary; resume with the same command.', flush=True)
        return 130
    result = dict(job=job, decisions=total, train_seconds=train_seconds, work_totals=work_totals, train_underlying_turns=work_totals[0], train_travel_uses=work_totals[1], train_travel_turns=work_totals[2],
                  final=history[-1], best_decisions=best['decisions'], best_score=best_score)
    store.json(folder/'result.json', result)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=pathlib.Path, default=ROOT/'learning-runs/ring-ablation-suite')
    ap.add_argument('--corpus', type=pathlib.Path, default=ROOT.parents[1]/'fixtures/d1-corpus-388')
    ap.add_argument('--variants', default=DEFAULT)
    ap.add_argument('--seeds', default='1,2')
    ap.add_argument('--steps', type=int, default=30_000_000)
    ap.add_argument('--baseline-steps', type=int, default=30_000_000)
    ap.add_argument('--checkpoint-every', type=int, default=1_000_000)
    ap.add_argument('--eval-per-map', type=int, default=32)
    ap.add_argument('--max-disk-gb', type=float, default=2)
    ap.add_argument('--min-free-gb', type=float, default=5)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--smoke', action='store_true')
    ap.add_argument('--performance', choices=('fast', 'reference'), default='fast',
                    help='Fast route BFS/kernel launches and skip completed evaluation worlds')
    ap.add_argument('--worker', help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.max_disk_gb <= 0 or args.min_free_gb < 0:
        ap.error('Disk budget must be positive and free reserve nonnegative')
    store = Store(args.output, int(args.max_disk_gb*GIB), int(args.min_free_gb*GIB))
    if args.worker:
        manifest = json.loads((store.root/'manifest.json').read_text())
        job = next(j for j in manifest['jobs'] if j['id'] == args.worker)
        return worker(store, manifest, job)
    jobs = jobs_for(args)
    print(json.dumps(dict(jobs=jobs, total_requested_decisions=sum(j['steps'] for j in jobs),
                          output=str(store.root), max_disk_gb=args.max_disk_gb,
                          free_space_reserve_gb=args.min_free_gb,
                          retention='one latest.pt and best.pt plus compact milestone weights; no map copies'), indent=2))
    if args.dry_run:
        return 0
    if (store.root.exists() and not (store.root/'manifest.json').exists()
            and any(p.name != '.lock' for p in store.root.iterdir())):
        raise ValueError('Output must be empty or an existing suite with manifest.json')
    store.root.mkdir(parents=True, exist_ok=True)
    with (store.root/'.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another runner owns this output directory')
        manifest = dict(format='ring-ablation-suite-v1', corpus=str(args.corpus.resolve()), jobs=jobs,
                        sources={p: digest(ROOT/p) for p in SOURCE_FILES},
                        maps=corpus_manifest(args.corpus.resolve()))
        manifest_path = store.root/'manifest.json'
        if manifest_path.exists():
            if json.loads(manifest_path.read_text()) != manifest:
                raise ValueError('Suite settings, source code, or corpus changed; use a new output directory')
        else:
            store.json('manifest.json', manifest)
        for job in jobs:
            result = store.root/'runs'/job['id']/'result.json'
            if result.exists():
                print('Already complete:', job['id'], flush=True)
                report_completed(json.loads(result.read_text()))
                continue
            build(store, job)
            build(store, dict(job, clump_mode=0))
            command = [sys.executable, str(pathlib.Path(__file__).resolve()), '--worker', job['id'],
                       '--output', str(store.root), '--max-disk-gb', str(args.max_disk_gb),
                       '--min-free-gb', str(args.min_free_gb)]
            child = subprocess.Popen(command)  # stream output; never grow an unbounded log
            try:
                code = child.wait()
            except KeyboardInterrupt:
                child.send_signal(signal.SIGTERM)
                child.wait()
                return 130
            if code:
                print(f'{job["id"]} exited {code}; stopped suite. Rerun the same command to resume.', flush=True)
                return code
            report_completed(json.loads(result.read_text()))
            results = [json.loads(p.read_text()) for p in sorted((store.root/'runs').glob('*/result.json'))]
            store.json('summary.json', results)
            print(f'Suite outputs: {store.used()/MIB:.1f} MiB', flush=True)
        results = [json.loads((store.root/'runs'/j['id']/'result.json').read_text()) for j in jobs]
        print(json.dumps(dict(status='suite_complete',
                              **timing_fields(sum(r['decisions'] for r in results),
                                              sum(r['train_seconds'] for r in results)))), flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (DiskBudgetError, OSError, ValueError, RuntimeError) as exc:
        print(f'Stopped safely: {exc}', file=sys.stderr)
        sys.exit(2)
