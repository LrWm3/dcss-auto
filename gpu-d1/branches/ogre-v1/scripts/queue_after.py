"""Run an ogre suite after a preceding suite completes successfully."""
import argparse
import fcntl
import json
import pathlib
import sys
import run_ring_ablations as runner


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--after-suite', type=pathlib.Path, required=True)
    args, remaining = parser.parse_known_args()
    runner.SOURCE_FILES = [*runner.SOURCE_FILES, 'scripts/queue_after.py']
    if '--dry-run' not in remaining:
        suite = args.after_suite.resolve()
        manifest = json.loads((suite/'manifest.json').read_text())
        print(f'Queued: waiting for {suite}', flush=True)
        with (suite/'.lock').open('r') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            for job in manifest['jobs']:
                path = suite/'runs'/job['id']/'result.json'
                if not path.exists() or json.loads(path.read_text())['decisions'] < job['steps']:
                    raise RuntimeError(f'Preceding suite stopped unfinished: {job["id"]}')
        print('Preceding suite complete; starting ogre feature screen.', flush=True)
    sys.argv = [sys.argv[0], *remaining]
    return runner.main()


if __name__ == '__main__':
    sys.exit(main())
