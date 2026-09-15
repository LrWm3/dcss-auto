"""Wait for the existing four-run budget queue, then run the 15x15 screen."""
import argparse
import fcntl
import json
from pathlib import Path
import sys
import run_ring_ablations as runner

def main():
    ap=argparse.ArgumentParser(add_help=False)
    ap.add_argument('--after-queue',type=Path,required=True)
    args,remaining=ap.parse_known_args()
    runner.SOURCE_FILES=[*runner.SOURCE_FILES,'scripts/queue_after_budget.py']
    if '--dry-run' not in remaining:
        plan_path=args.after_queue.resolve();plan=json.loads(plan_path.read_text())
        print('Queued: waiting for',plan_path,flush=True)
        with plan_path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            for job in plan['jobs']:
                path=Path(job['result'])
                if not path.exists() or json.loads(path.read_text())['decisions']<30_000_000:
                    raise RuntimeError('Preceding run did not finish: '+job['name'])
        print('Preceding queue complete; starting 15x15 vision comparison.',flush=True)
    sys.argv=[sys.argv[0],*remaining]
    return runner.main()

if __name__=='__main__':sys.exit(main())
