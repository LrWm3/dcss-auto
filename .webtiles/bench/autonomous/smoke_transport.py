"""Small fixed-seed transport smoke check; not a policy-strength benchmark."""
import argparse
import json
from pathlib import Path
import time

from general_env import GeneralEnvironment, sha, ENGINE
from teacher import choose_action


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    reference = json.loads(args.reference.read_text()) if args.reference else None
    started = time.perf_counter()
    runs = []
    for index, seed in enumerate(['1760771545328102746', '1760771545328102747']):
        env = GeneralEnvironment(args.output / f'game-{index}', seed=seed)
        try:
            t = time.perf_counter()
            state = env.launch()
            reset_seconds = time.perf_counter() - t
            observations, actions, step_seconds = [state], [], 0.0
            for decision in range(40):
                if state.get('terminal'):
                    break
                action = reference['runs'][index]['actions'][decision] if reference else state['actions'][choose_action(state)]
                t = time.perf_counter()
                state = env.step(action)
                step_seconds += time.perf_counter() - t
                actions.append(action)
                observations.append(state)
            checkpoint = args.output / f'checkpoint-{index}'
            env.save_state(checkpoint)
            t = time.perf_counter()
            restored = env.launch(checkpoint)
            restore_seconds = time.perf_counter() - t
            runs.append(dict(seed=seed, actions=actions, observations=observations,
                             restored=restored, reset_seconds=reset_seconds,
                             restore_seconds=restore_seconds, step_seconds=step_seconds))
        finally:
            env.close()
    matched = None if not reference else all(
        a['observations'] == b['observations'] and a['restored'] == b['restored']
        for a,b in zip(runs, reference['runs']))
    result = dict(runs=runs, matched=matched, elapsed_seconds=time.perf_counter()-started,
                  actions_per_second=sum(len(r['actions']) for r in runs)/sum(r['step_seconds'] for r in runs),
                  engine_sha256=sha(ENGINE), adapter_sha256=sha(Path(__file__).with_name('general_env.py')))
    (args.output / 'results.json').write_text(json.dumps(result))
    print(json.dumps({k:v for k,v in result.items() if k!='runs'}), flush=True)
    if matched is False:
        raise SystemExit('Gameplay observation mismatch')


if __name__ == '__main__':
    main()
