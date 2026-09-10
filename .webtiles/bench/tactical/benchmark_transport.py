"""Fixed-action transport benchmark; never edits historical cases or adapters."""
import argparse
import hashlib
import json
import time
from pathlib import Path

from bench import HERE, sha
import bench
from goal_env import GoalEnvironment
from character_dataset import canonical

FAMILIES = ('fresh-evaluation/collection/encounter-015',
            'fresh-evaluation/supplemental/encounter-034')

class NoDelayEnvironment(GoalEnvironment):
    def await_state(self, *args, **kwargs):
        self.child.delaybeforesend = None
        return super().await_state(*args, **kwargs)

def digest(state):
    return hashlib.sha256(json.dumps(canonical(state), sort_keys=True).encode()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--mode', choices=['baseline', 'no-delay', 'fast'], default='baseline')
    p.add_argument('--steps', type=int, default=60)
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--policy', choices=['pursue_no_berserk', 'candidate'], default='pursue_no_berserk')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cls = GoalEnvironment
    if args.mode == 'no-delay':
        cls = NoDelayEnvironment
    if args.mode == 'fast':
        from fast_env import FastEnvironment, derive_fast
        bench.ENGINE = bench.ENGINE.with_name('crawl-tactical-fast')
        cls = FastEnvironment
    results = []
    for family in FAMILIES:
        root = HERE/'artifacts/goals-character-v2-holdout-v4'/family
        trace = next((root/args.policy).glob('worker-*/transitions.jsonl'))
        rows = [json.loads(line) for line in trace.read_text().splitlines()][:args.steps]
        case = root/'rich-case'
        if args.mode == 'fast':
            case = derive_fast(case, args.output/'cases'/family)
        for repeat in range(args.repeats):
            env = cls(args.output/'workers')
            result = dict(family=family, repeat=repeat, mode=args.mode,
                          source_trace=str(trace), source_sha256=sha(trace))
            try:
                start = time.perf_counter()
                state = env.reset(case)
                result['startup_seconds'] = time.perf_counter()-start
                assert digest(state) == digest(rows[0]['observation']), 'Initial mismatch'
                latencies, hashes = [], [digest(state)]
                for index, row in enumerate(rows):
                    start = time.perf_counter()
                    state = env.step(row['action'])
                    latencies.append(time.perf_counter()-start)
                    hashes.append(digest(state))
                    assert hashes[-1] == digest(row['next_observation']), f'Mismatch at {index}'
                result.update(steps=len(latencies), seconds=sum(latencies),
                              actions_per_second=len(latencies)/sum(latencies),
                              latencies=latencies, state_hashes=hashes, equivalent=True,
                              endpoint=state.get('terminal', 'alive'))
            finally:
                env.close()
                result['worker'] = str(env.work)
                result['worker_bytes'] = sum(f.stat().st_size for f in env.work.rglob('*') if f.is_file())
                results.append(result)
                (args.output/'results.json').write_text(json.dumps(results, indent=2)+'\n')
                print(json.dumps({k:v for k,v in result.items() if k not in ('latencies','state_hashes')}), flush=True)

if __name__ == '__main__':
    main()
