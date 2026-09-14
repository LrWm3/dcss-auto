"""Live score, exact restore, cutoff and terminal reporting checks."""
import os
for key in ('DCSS_EXPLORATION_SCORE', 'DCSS_HEALTH_FEATURES', 'DCSS_REST_ONLY', 'DCSS_VISIT_MEMORY'):
    os.environ[key] = '1'
os.environ['DCSS_REPRESENTATION'] = 'spatial-v6'
os.environ['DCSS_GENERAL_RNG_DIAGNOSTICS'] = '1'
import argparse
from pathlib import Path
import torch
from general_env import GeneralEnvironment
from teacher import choose_action
from collect import run_episode
from bootstrap_repair import write
from exploration_score import components
import storage


def check(state):
    expected = components(state['score'], state['exploration_raw'])
    for key, value in expected.items():
        assert state[key] == value, (key, state.get(key), value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve(); root.mkdir(parents=True, exist_ok=False)
    storage.configure(root); torch.set_num_threads(1)
    env = GeneralEnvironment(root / 'live', seed='60917000', data_role='diagnostic')
    env.record_events = False
    samples = []
    try:
        state = env.reset(); check(state)
        assert state['exploration_raw'] > 0
        for _ in range(25):
            state = env.step(choose_action(state)); check(state)
            samples.append({k: state[k] for k in ('score','training_score','exploration_raw','turn')})
        assert samples[-1]['exploration_raw'] > samples[0]['exploration_raw']
        before = dict(state)
        env.save_state(root/'checkpoint')
        assert env.state == before
        sequences = []
        for _ in range(2):
            s = env.reset(root/'checkpoint'); check(s)
            assert s['exploration_raw'] == before['exploration_raw']
            sequence = []
            for _ in range(8):
                s = env.step(choose_action(s)); check(s); sequence.append(s)
            sequences.append(sequence)
        assert sequences[0] == sequences[1], 'restore divergence'
    finally:
        env.close(); storage.finish_logs(env.works)
    model = Path(__file__).parent/'artifacts/v6-visits-01/candidate.pt'
    outcomes = []
    for name, steps in (('cutoff',10), ('death',500)):
        r = run_episode(root/name, '16140901064556770664', steps,
            model_path=model, total_steps=steps, epsilon=0, snapshot=False, data_role='screen')
        check(r)
        assert r['truncated'] if name == 'cutoff' else r['terminal_kind'] == 'death'
        outcomes.append(r)
    write(root/'results.json', {'passed': True, 'live_samples': samples,
        'deterministic_restore_steps': 8, 'outcomes': outcomes})
    print('Live exploration, snapshot determinism, cutoff and death checks passed')


if __name__ == '__main__':
    main()
