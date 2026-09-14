"""Bounded REST-only experiment. No training or automatic promotion."""
import os
os.environ['DCSS_REPRESENTATION'] = 'spatial-v6'
os.environ['DCSS_HEALTH_FEATURES'] = '1'
os.environ['DCSS_REST_ONLY'] = '1'
import argparse
from pathlib import Path
import torch
from model import ActionValueModel, save_model
from general_env import GeneralEnvironment
from teacher import choose_action, _actions
from bootstrap_repair import play_batch, write


def validate(state):
    actions = _actions(state)
    assert all(a['kind'] != 'WAIT' for a in actions)
    if any(a['kind'] == 'REST' for a in actions):
        p = state['player']
        assert p['hp'] < p['max_hp']
        assert not state.get('monsters')


def smoke(root):
    env = GeneralEnvironment(root / 'smoke', data_role='diagnostic')
    env.record_events = False
    rests = []
    checks = {'full_hp': 0, 'visible_enemies': 0, 'states': 0}
    try:
        state = env.reset()
        for _ in range(1000):
            if state.get('terminal'):
                break
            validate(state)
            checks['states'] += 1
            checks['full_hp'] += state['player']['hp'] == state['player']['max_hp']
            checks['visible_enemies'] += bool(state.get('monsters'))
            index = choose_action(state)
            action = _actions(state)[index]
            after = env.step(index)
            if action['kind'] == 'REST':
                rests.append({'before_hp': state['player']['hp'],
                              'after_hp': after.get('player', {}).get('hp'),
                              'before_turn': state.get('turn'), 'after_turn': after.get('turn'),
                              'enemies_after': bool(after.get('monsters')),
                              'result': after.get('last_action_result')})
            state = after
            if len(rests) >= 3:
                break
        assert rests, 'no REST exercised'
        assert checks['full_hp'] and checks['visible_enemies']
        assert any(r['after_turn'] - r['before_turn'] > 1 for r in rests), rests
        result = {'passed': True, 'checks': checks, 'rests': rests}
        write(root / 'smoke.json', result)
        return result
    finally:
        env.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--initial', type=Path, required=True)
    parser.add_argument('--smoke-only', action='store_true')
    args = parser.parse_args()
    torch.set_num_threads(1)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    write(root / 'latest_status.json', {'phase': 'smoke', 'training': False})
    try:
        smoke(root)
        if args.smoke_only:
            write(root / 'latest_status.json', {'phase': 'smoke_complete'})
            return
        payload = torch.load(args.initial, map_location='cpu', weights_only=False)
        assert payload['feature_version'] == 'general-features-v6-spatial-entities-health-v1'
        model = ActionValueModel(hidden=payload['hidden'])
        model.load_state_dict(payload['state_dict'])
        model.eval()
        checkpoint = root / 'rest-initial.pt'
        save_model(checkpoint, model, {'source': str(args.initial.resolve()),
                   'migration': 'Explicit WAIT-to-REST slot initialization; no retraining. Historical WAIT replay is not REST data.'})
        seeds = [str(16140901064556770664 + i) for i in range(5)]
        write(root / 'latest_status.json', {'phase': 'five_game_test', 'seeds': seeds,
              'decisions_per_game': 2000, 'checkpoint': str(checkpoint), 'training': False})
        results = play_batch(root / 'games', checkpoint, seeds, False, steps=2000)
        write(root / 'latest_status.json', {'phase': 'complete', 'results': results,
              'training': False, 'promoted': False})
    except BaseException as exc:
        write(root / 'latest_status.json', {'phase': 'failed', 'error': repr(exc)})
        raise


if __name__ == '__main__':
    main()
