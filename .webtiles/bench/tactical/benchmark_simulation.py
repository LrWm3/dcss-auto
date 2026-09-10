"""Equal-work process scaling and presentation ablations on immutable replays."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import multiprocessing
import os
from pathlib import Path
import resource
import statistics
import time

import bench
from benchmark_transport import FAMILIES, digest
from fast_env import FastEnvironment, derive_fast

def trial(task):
    bench.ENGINE = Path(task['engine'])
    os.environ['DCSS_TACTICAL_SIM_FLAGS'] = str(task['flags'])
    rows = [json.loads(line) for line in Path(task['trace']).read_text().splitlines()][:task['steps']]
    expected = [digest(rows[0]['observation'])] + [digest(r['next_observation']) for r in rows]
    cls = FastEnvironment
    if task.get('cache_template'):
        from cached_env import CachedEnvironment
        cls = CachedEnvironment
        os.environ['DCSS_TACTICAL_CACHE_TEMPLATE'] = task['cache_template']
    env = cls(Path(task['output'])/f"trial-{task['id']:03d}")
    result = {k:task[k] for k in ('id','family','flags','trace','case')}
    cpu_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    python_before = time.process_time()
    wall = time.perf_counter()
    latencies, hashes = [], []
    try:
        state = env.reset(task['case'])
        result['startup_seconds'] = time.perf_counter()-wall
        hashes.append(digest(state))
        if hashes[-1] != expected[0]:
            raise RuntimeError('Initial state divergence')
        for index, row in enumerate(rows):
            start = time.perf_counter()
            state = env.step(row['action'])
            latencies.append(time.perf_counter()-start)
            hashes.append(digest(state))
            if hashes[-1] != expected[index+1]:
                raise RuntimeError(f'Gameplay divergence at action {index+1}')
        result.update(equivalent=True, endpoint=state.get('terminal','alive'))
    except Exception as exc:
        result.update(equivalent=False, error=repr(exc))
    finally:
        try:
            env.close()
        except Exception as exc:
            result.update(equivalent=False, close_error=repr(exc))
        cpu_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        result.update(wall_seconds=time.perf_counter()-wall, steps=len(latencies),
            step_seconds=sum(latencies), state_hashes=hashes,
            python_cpu_seconds=time.process_time()-python_before,
            engine_cpu_seconds=(cpu_after.ru_utime+cpu_after.ru_stime
                                -cpu_before.ru_utime-cpu_before.ru_stime),
            worker=str(getattr(env,'work','')),
            step_p50=statistics.median(latencies) if latencies else None)
        work = Path(result['worker'])
        if (work/'run.json').exists():
            manifest = json.loads((work/'run.json').read_text())
            manifest['simulation_flags'] = task['flags']
            (work/'run.json').write_text(json.dumps(manifest, indent=2)+'\n')
        (Path(task['output'])/f"trial-{task['id']:03d}"/'result.json').write_text(
            json.dumps(result, indent=2)+'\n')
    return result

def summarize(rows, seconds):
    return dict(trials=len(rows), equivalent=all(r['equivalent'] for r in rows),
        steps=sum(r['steps'] for r in rows), batch_seconds=seconds,
        batch_actions_per_second=sum(r['steps'] for r in rows)/seconds,
        per_worker_step_actions_per_second=sum(r['steps'] for r in rows)/sum(r['step_seconds'] for r in rows),
        mean_startup_seconds=statistics.mean(r['startup_seconds'] for r in rows if 'startup_seconds' in r),
        engine_cpu_seconds=sum(r['engine_cpu_seconds'] for r in rows),
        python_cpu_seconds=sum(r['python_cpu_seconds'] for r in rows))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--engine', type=Path, default=bench.ENGINE.with_name('crawl-tactical-sim'))
    p.add_argument('--workers', type=int, nargs='+', default=[1,2,4,6])
    p.add_argument('--flags', type=int, nargs='+', choices=[0,1,2,3], default=[0])
    p.add_argument('--jobs', type=int, default=12)
    p.add_argument('--steps', type=int, default=60)
    p.add_argument('--policy', choices=['pursue_no_berserk','candidate'], default='pursue_no_berserk')
    p.add_argument('--cache-template', type=Path)
    args = p.parse_args()
    if args.jobs < 2 or args.jobs % 2 or min(args.workers)<1:
        p.error('Use a positive even job count and positive workers')
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'benchmark_simulation.py').write_bytes(Path(__file__).read_bytes())
    bench.ENGINE = args.engine.resolve()
    families = []
    for family in FAMILIES:
        root = bench.HERE/'artifacts/goals-character-v2-holdout-v4'/family
        case = derive_fast(root/'rich-case', args.output/'cases'/family)
        trace = next((root/args.policy).glob('worker-*/transitions.jsonl'))
        families.append(dict(family=family, case=str(case), trace=str(trace)))
    report = dict(engine=str(bench.ENGINE),engine_sha256=bench.sha(bench.ENGINE),
                  benchmark_sha256=bench.sha(Path(__file__)),
                  cache_template=str(args.cache_template.resolve()) if args.cache_template else None,
                  groups=[])
    for flags in args.flags:
        for workers in args.workers:
            output = args.output/f'flags-{flags}-workers-{workers}'
            output.mkdir()
            tasks = [dict(**families[i%2], id=i, engine=str(bench.ENGINE),
                          flags=flags, steps=args.steps, output=str(output),
                          cache_template=report['cache_template']) for i in range(args.jobs)]
            rows = []
            start = time.perf_counter()
            with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn')) as pool:
                for future in as_completed([pool.submit(trial,t) for t in tasks]):
                    row = future.result()
                    rows.append(row)
                    (output/'trials.json').write_text(json.dumps(rows, indent=2)+'\n')
                    print(json.dumps(dict(flags=flags,workers=workers,completed=len(rows),
                        id=row['id'],steps=row['steps'],equivalent=row['equivalent'],error=row.get('error'))),flush=True)
            summary = summarize(rows, time.perf_counter()-start)
            summary.update(flags=flags, workers=workers)
            report['groups'].append(summary)
            (args.output/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
            print(json.dumps(summary),flush=True)
            if not summary['equivalent']:
                raise SystemExit('Stop: replay verification failed; evidence retained')

if __name__ == '__main__':
    main()
