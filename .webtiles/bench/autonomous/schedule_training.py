"""Run resumable one-cycle jobs until a wall-clock deadline.

The supervisor is deliberately outside the training lock. If another training
job is active, its one-cycle attempt exits quickly and the supervisor retries;
the active job is never interrupted.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--hours', type=float, required=True)
    parser.add_argument('--poll-seconds', type=float, default=30)
    args = parser.parse_args()
    root = args.run_dir.resolve()
    deadline = time.time() + args.hours * 3600
    schedule = root / 'schedule.json'
    log = root / 'metrics' / 'scheduled-training.log'
    write(schedule, {'state':'scheduled', 'policy':'one-resumable-cycle-at-a-time',
                     'started_unix':time.time(), 'deadline_unix':deadline,
                     'hours':args.hours, 'poll_seconds':args.poll_seconds,
                     'pid':__import__('os').getpid()})
    log.parent.mkdir(parents=True, exist_ok=True)
    train = Path(__file__).resolve().with_name('train_crawl_agent.py')
    while time.time() < deadline:
        remaining = deadline - time.time()
        command = [sys.executable, str(train), '--run-dir', str(root), '--cycles', '1']
        started = time.time()
        with log.open('a') as stream:
            stream.write(json.dumps({'event':'launch_attempt','time':started,
                                     'remaining_seconds':remaining})+'\n')
            stream.flush()
            process = subprocess.run(command, cwd=str(train.parent.parent.parent.parent),
                                     stdout=stream, stderr=subprocess.STDOUT)
        with log.open('a') as stream:
            stream.write(json.dumps({'event':'launch_finished','time':time.time(),
                                     'returncode':process.returncode})+'\n')
        if time.time() >= deadline:
            break
        time.sleep(min(args.poll_seconds, max(0, deadline-time.time())))
    write(schedule, {'state':'complete', 'policy':'one-resumable-cycle-at-a-time',
                     'started_unix':schedule.exists() and json.loads(schedule.read_text()).get('started_unix'),
                     'deadline_unix':deadline, 'finished_unix':time.time(),
                     'hours':args.hours})


if __name__ == '__main__':
    main()
