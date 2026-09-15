"""Run the route-cue exploration-reward ablation after an existing suite.

Keep this extension separate so the running suite's source hashes stay valid.
Remaining arguments are passed to run_ring_ablations (including --dry-run).
"""
import argparse
import fcntl
import json
import pathlib
import sys

import run_ring_ablations as runner


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--after-suite', type=pathlib.Path)
    args, remaining = parser.parse_known_args()
    runner.VARIANTS['route_no_explore'] = dict(frontier=True, route_cue=True,
                                              explore_milli=0)
    runner.SOURCE_FILES = [*runner.SOURCE_FILES, 'scripts/run_route_no_explore.py']
    if args.after_suite and '--dry-run' not in remaining:
        suite = args.after_suite.resolve()
        manifest = json.loads((suite / 'manifest.json').read_text())
        print(f'Queued: waiting for {suite}', flush=True)
        with (suite / '.lock').open('r') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            for job in manifest['jobs']:
                path = suite / 'runs' / job['id'] / 'result.json'
                if not path.exists() or json.loads(path.read_text())['decisions'] < job['steps']:
                    raise RuntimeError(f'Preceding suite stopped unfinished: {job["id"]}')
        print('Preceding suite complete; starting route_no_explore.', flush=True)
    sys.argv = [sys.argv[0], '--variants', 'route_no_explore', *remaining]
    return runner.main()


if __name__ == '__main__':
    sys.exit(main())
