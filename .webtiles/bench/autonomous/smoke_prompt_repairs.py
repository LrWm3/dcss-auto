"""Replay historical faith/invisibility blocks with the current bridge."""
import argparse
import json
import shutil
import time
from general_env import GeneralEnvironment, make_rc


def run(source, output):
    found = {}
    for path in sorted((source / 'state_archive').glob('*/case.json')):
        data = json.loads(path.read_text())
        for a in GeneralEnvironment._normalise_actions(data['observation']):
            kind = ('faith' if a['kind'] == 'REMOVE' and 'faith' in a.get('item_name', '') else
                    'invis' if a['kind'] == 'USE_ABILITY' and 'invis' in a.get('name', '').lower() else None)
            if kind and kind not in found:
                found[kind] = (path.parent, a)
    assert set(found) == {'faith', 'invis'}, found
    results = []
    for kind, (case, intended) in found.items():
        migrated = output / kind / 'fixture'
        shutil.copytree(case, migrated)
        make_rc(migrated / 'trial.rc')
        env = GeneralEnvironment(output / kind / 'live')
        try:
            before = env.launch(migrated)
            action = next(a for a in env.legal_actions() if a['kind'] == intended['kind']
                          and (a.get('slot') == intended['slot'] if kind == 'faith'
                               else a.get('name') == intended['name']))
            started = time.monotonic()
            after = env.step(action)
            assert after['seq'] == before['seq'] + 1
            if kind == 'faith':
                inventory = after['inventory']
                if isinstance(inventory, dict):
                    inventory = inventory.values()
                assert not any(i.get('slot') == action['slot'] and i.get('equipped') for i in inventory)
            else:
                assert 'invisible' in str(after.get('status', '')).lower(), after.get('status')
            results.append({'fixture':str(case), 'kind':kind, 'action':action,
                            'seconds':time.monotonic()-started,
                            'turn_before':before['turn'], 'turn_after':after['turn'],
                            'last_action_result':after.get('last_action_result'), 'passed':True})
        finally:
            env.close()
    (output / 'results.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    run(args.source, args.output)
