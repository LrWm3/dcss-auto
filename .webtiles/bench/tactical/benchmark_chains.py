"""No-healing synthetic encounter chains. Evaluation only, no model fitting.

Different waves share one checkpoint character and its current battlefield.
Only native monster construction happens between waves; combat state persists.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import multiprocessing as mp
import os
from pathlib import Path
import shutil

import bench
from action_env import ActionEnv, ACTIONS, fixed_action
from audit_action_episodes import audit
from cached_env import prepare_cache
from fast_env import FastEnvironment
from goal_controllers import Recovery, dist
from prepare_berserk_timing_fresh import advance_hook
from rich_features import values

HERE = Path(__file__).resolve().parent
POLICIES = ('never', 'every_wave', 'last_wave')
SAFE_WAVE_MONSTERS = {'hound', 'iguana', 'ogre', 'orc warrior'}


def save(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2)+'\n')


class ChainRecovery(Recovery):
    def observe(self, before, after):
        c = after['chain']
        if c['stage'] != c['total'] or c['native']['alive']:
            self.quiet = 0
            return False
        return super().observe(before, after)


def choose(state, mask, policy, activated):
    c = state['chain']
    enabled = policy == 'every_wave' or (policy == 'last_wave' and c['stage'] == c['total'])
    near = any(dist((e['x'], e['y'])) <= 2 for e in values(state.get('monsters')))
    if enabled and c['stage'] not in activated and mask[-1] and near:
        return ACTIONS.index('berserk')
    return fixed_action(state, mask, 'pursue')


def check_boundary(boundary):
    before, after = boundary['before'], boundary['after']
    for key in ('turn', 'hp', 'max_hp', 'mp', 'max_mp', 'x', 'y', 'durations'):
        if before[key] != after[key]:
            raise ValueError('Player changed at wave boundary: '+key)
    for key in ('elapsed_time', 'berserk_penalty'):
        if before.get(key) != after.get(key):
            raise ValueError('Player changed at wave boundary: '+key)
    if before['alive'] or after['alive'] <= 0:
        raise ValueError('Wave advanced with survivors or spawned nothing')


def trial(task):
    config, root, index, policy, max_steps = task
    os.environ['DCSS_TACTICAL_CHAIN'] = '1'
    env = ActionEnv(config, Path(root)/policy/f'case-{index:03d}', max_steps=max_steps)
    result = dict(index=index, policy=policy, outcome='harness_error')
    boundaries, attempts, activated = [], [], set()
    try:
        env.reset(options={'case_index':index})
        env.recovery = ChainRecovery()
        result.update(waves=env.entry['waves'], chain_length=len(env.entry['waves']),
                      seed=env.entry['seed'], rng_offset=env.entry['rng_offset'],
                      initial_player=env.state['player'], initial_hp=env.state['hp'])
        last_chain = env.state['chain']
        for _ in range(max_steps):
            state = env.state
            boundary = state['chain'].get('boundary')
            if boundary:
                check_boundary(boundary)
                boundaries.append(boundary)
            mask = env.action_masks()
            action = choose(state, mask, policy, activated)
            _, _, done, truncated, _ = env.step(action)
            if action == ACTIONS.index('berserk'):
                success = bool(env.state.get('berserk')) and not state.get('berserk')
                attempts.append(dict(stage=state['chain']['stage'], turn=state['turn'],
                                     activated=success))
                if success:
                    activated.add(state['chain']['stage'])
            if not env.state.get('terminal'):
                last_chain = env.state['chain']
            if done or truncated:
                break
        result.update(json.loads((env.transport.work/'episode.json').read_text()))
        if result['outcome'] == 'recovered_quiet' and (
                last_chain['stage'] != last_chain['total'] or last_chain['native']['alive']):
            raise ValueError('Premature recovery')
        # Standard auditor plus chain-specific native boundary invariants.
        audit(env.transport.work/'episode.json', recovery_factory=ChainRecovery)
        result.update(cleared=last_chain['stage'] - int(last_chain['native']['alive'] > 0),
                      boundaries=boundaries, attempts=attempts, activations=len(activated))
    except Exception as exc:
        result.update(outcome='harness_error', error=repr(exc),
                      worker=str(getattr(env.transport, 'work', '')))
    finally:
        env.close()
    return result


def prepare(parent, root, engine, seeds, offsets, recipes=None, offset_start=0):
    old = json.loads(parent.read_text())
    if old.get('test_used'):
        raise ValueError('Do not derive from test data')
    origins = [e for e in old['cases'] if e['split']=='train'
               and e['rng_offset']==0 and e['seed'] in seeds]
    if {e['seed'] for e in origins} != set(seeds):
        raise ValueError('Missing training seed')
    root.mkdir(parents=True, exist_ok=False)
    bench.ENGINE = engine
    engine_hash = bench.sha(engine)
    entries = []
    recipes = recipes or [[['hound'], ['ogre']], [['hound'], ['iguana'], ['ogre']]]
    if offsets < 1 or offset_start < 0 or any(len(r) not in (2,3) or any(not w or len(w)>8 for w in r) for r in recipes):
        raise ValueError('Expected nonempty two/three-wave recipes and positive offsets')
    if len({len(r) for r in recipes}) != len(recipes):
        raise ValueError('Use one recipe per chain length in a benchmark')
    if any(n not in SAFE_WAVE_MONSTERS for r in recipes for w in r for n in w):
        raise ValueError('Unaudited monster: summoners and special death effects need broader wave tracking')
    for origin in origins:
        case = Path(origin['case'])
        meta = json.loads((case/'case.json').read_text())
        for name, key in [('checkpoint.cs','save_sha256'), ('trial.rc','rc_sha256')]:
            if bench.sha(case/name) != meta[key]:
                raise ValueError('Parent changed')
        for recipe in recipes:
            for reverse in (False, True):
                waves = list(reversed(recipe)) if reverse else recipe
                for offset in range(offset_start, offset_start + offsets):
                    dest = root/'cases'/f'{origin["seed"]}-{len(waves)}-{int(reverse)}-{offset}'
                    dest.mkdir(parents=True)
                    shutil.copy2(case/'checkpoint.cs', dest/'checkpoint.cs')
                    source = advance_hook((case/'trial.rc').read_text(), offset)
                    needle = 'function tactical_dump()\n'
                    if source.count(needle) != 1:
                        raise ValueError('Unknown dump hook')
                    source = source.replace(needle, needle+'  chain_tick()\n')
                    lua_waves = '{'+','.join('{'+','.join(json.dumps(n) for n in w)+'}' for w in waves)+'}'
                    hook = '\nCHAIN_WAVES='+lua_waves+'\nCHAIN_SETUP_SEED=91301\n'+(HERE/'chain_bridge.lua').read_text()
                    at = source.rfind('\n>')
                    if at < 0:
                        raise ValueError('Missing Lua block')
                    (dest/'trial.rc').write_text(source[:at]+hook+source[at:])
                    save(dest/'case.json', dict(meta, engine_sha256=engine_hash,
                        rc_sha256=bench.sha(dest/'trial.rc'), parent_case=str(case),
                        training_ready=False, synthetic_chain=True, waves=waves))
                    entries.append(dict(origin, id=dest.name, case=str(dest), waves=waves,
                                        rng_offset=offset, initial_hash=None))
    # Build engine-specific caches from an actual uncached launch, not by
    # relabelling another binary's cache manifest.
    os.environ.update(DCSS_TACTICAL_CHAIN='1', DCSS_TACTICAL_AUGMENT='1', DCSS_TACTICAL_SIM_FLAGS='3')
    env = FastEnvironment(root/'bootstrap')
    try:
        state = env.reset(entries[0]['case'])
        check_boundary(state['chain']['boundary'])
        save(root/'bootstrap-state.json', state)
    finally:
        env.close()
    cache = prepare_cache(env.work, root/'cache')
    cfg = dict(version=1, engine=str(engine), engine_sha256=engine_hash,
               cache=str(cache), cases=entries, test_used=False, training_ready=False,
               parent=str(parent), parent_sha256=bench.sha(parent),
               runner_sha256=bench.sha(Path(__file__)),
               chain_bridge_sha256=bench.sha(HERE/'chain_bridge.lua'))
    save(root/'config.json', cfg)
    return root/'config.json'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent', type=Path, default=HERE/'artifacts/action-direction-cycle-v1/config.json')
    p.add_argument('--engine', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--seeds', nargs='+', default=['83017001','83019003','83018003'])
    p.add_argument('--offsets', type=int, default=2)
    p.add_argument('--offset-start', type=int, default=0,
                   help='First gameplay RNG advance count (default: 0)')
    p.add_argument('--workers', type=int, default=6)
    p.add_argument('--max-steps', type=int, default=320)
    p.add_argument('--recipes', type=Path, help='JSON list of two/three-wave monster-name lists')
    p.add_argument('--config', type=Path, help='Reuse prepared cases into a new result directory')
    args = p.parse_args()
    root = args.output.resolve()
    if args.config:
        root.mkdir(parents=True, exist_ok=False)
        config = args.config.resolve()
    else:
        recipes = json.loads(args.recipes.read_text()) if args.recipes else None
        config = prepare(args.parent.resolve(), root, args.engine.resolve(), args.seeds,
                         args.offsets, recipes, args.offset_start)
    cfg = json.loads(config.read_text())
    tasks = [(str(config),str(root/'runs'),i,policy,args.max_steps)
             for i in range(len(cfg['cases'])) for policy in POLICIES]
    results = []
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=mp.get_context('spawn')) as pool:
        for future in as_completed([pool.submit(trial,t) for t in tasks]):
            row = future.result()
            results.append(row)
            save(root/'trials.json', results)
            print(json.dumps(dict(completed=len(results), total=len(tasks),
                                  policy=row['policy'], outcome=row['outcome'],
                                  error=row.get('error'))), flush=True)
    summary = {policy:dict(Counter(r['outcome'] for r in results if r['policy']==policy))
               for policy in POLICIES}
    save(root/'summary.json', summary)
    print(json.dumps(summary), flush=True)
    if any(r['outcome']=='harness_error' for r in results):
        raise RuntimeError('Incomplete benchmark: harness errors are not gameplay losses')


if __name__ == '__main__':
    main()
