"""Reuse training-only branches; gate bounded refit on candidate continuations."""
import argparse
import concurrent.futures
import gzip
import json
import random
from pathlib import Path

# Establish representation flags before importing the environment/model.
from try_visit_memory import fit, migrate, summary
from bootstrap_repair import play_batch, write
from general_env import GeneralEnvironment, ENGINE, sha
from model import save_model
from policy import Policy
from teacher import _actions
from data_split import assert_training_seed
import storage
import torch


def loop_tick(state, actions):
    """Diagnostic only: never masks or overrides policy actions."""
    if len(actions) < 4 or state.get('monsters'):
        return False
    recent = actions[-4:]
    if not all(a.get('kind') in ('MOVE', 'REMOVE', 'WEAR') for a in recent):
        return False
    if recent[0] != recent[2] or recent[1] != recent[3]:
        return False
    memory = state.get('visit_memory') or {}
    return memory.get('since_discovery', 0) >= 24 and memory.get('since_new_tile', 0) >= 24


def continuation(case, root, model, steps=256):
    metadata = json.loads((case/'case.json').read_text())
    assert_training_seed(metadata['seed'])
    if metadata.get('data_role', 'training') != 'training':
        raise ValueError('screen checkpoint must be training-only')
    env = GeneralEnvironment(root, data_role='training')
    env.record_events = False
    actions, loops = [], 0
    try:
        state = env.reset(case)
        policy = Policy(model, epsilon=0)
        initial_score = state.get('training_score')
        for _ in range(steps):
            if state.get('terminal'):
                break
            idx = policy.choose(state)[0]
            actions.append(_actions(state)[idx])
            state = env.step(idx)
            loops += int(loop_tick(state, actions))
        result = {'case': str(case), 'steps': len(actions), 'loop_ticks': loops,
                  'equipment_actions': sum(a['kind'] in ('WEAR', 'REMOVE') for a in actions),
                  'initial_training_score': initial_score, 'score': state.get('score'),
                  'training_score': state.get('training_score'), 'terminal': state.get('terminal'),
                  'final_level': state.get('level'), 'last_actions': actions[-8:]}
    except Exception as exc:
        result = {'case': str(case), 'error': repr(exc)}
    finally:
        env.close()
        storage.finish_logs(env.works)
    write(root/'screen-result.json', result)
    return result


def screen_gate(before, after):
    reasons = []
    if len(before) != len(after) or not before or any('error' in x for x in before+after):
        return {'passed': False, 'reasons': ['invalid or incomplete continuations']}
    for old, new in zip(before, after):
        if old['case'] != new['case']:
            return {'passed': False, 'reasons': ['unpaired cases']}
        if new['loop_ticks'] > old['loop_ticks'] + 16:
            reasons.append('increased repeated-action loop: '+new['case'])
        if new['equipment_actions'] > old['equipment_actions'] + max(8, .02*new['steps']):
            reasons.append('increased equipment cycling: '+new['case'])
    for key in ('score', 'training_score'):
        if any(not isinstance(x.get(key), (float, int)) for x in before+after):
            reasons.append('missing '+key)
        elif sum(x[key] for x in after) < .9*sum(x[key] for x in before):
            reasons.append('more than 10% screen regression: '+key)
    return {'passed': not reasons, 'reasons': reasons,
            'warning': 'small training-state safety screen; not evidence of held-out improvement'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fit-only', action='store_true')
    args = parser.parse_args()
    source, root = args.source.resolve(), args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    storage.configure(root)
    torch.set_num_threads(1)
    torch.manual_seed(17)
    status = {'phase': 'training', 'promoted': False}
    def update(**values):
        status.update(values)
        write(root/'latest_status.json', status)
    update(source=str(source))
    try:
        baseline = source/'initial.pt'
        config = json.loads((source/'config.json').read_text())
        if config['engine_sha256'] != sha(ENGINE):
            raise ValueError('source engine differs; cannot reuse paired baseline results')
        groups = []
        for path in sorted(source.glob('counterfactual-*.json.gz')):
            with gzip.open(path, 'rt') as stream:
                groups.append(json.load(stream))
        anchors = []
        for path in sorted((source/'collection').glob('*/anchors.json.gz')):
            assert_training_seed(path.parent.name)
            with gzip.open(path, 'rt') as stream:
                anchors.extend(json.load(stream))
        for group in groups:
            meta = json.loads((Path(group[0]['case'])/'case.json').read_text())
            assert_training_seed(meta['seed'])
            if meta.get('data_role', 'training') != 'training':
                raise ValueError('non-training branch')
        random.Random(17).shuffle(anchors)
        model = migrate(baseline)
        write(root/'config.json', {'source': str(source), 'initial_sha256': sha(baseline),
              'engine_sha256': sha(ENGINE), 'protocol': 'conservative-retry-v1',
              'screen_cases': 8, 'screen_steps': 256, 'evaluation_count': 5,
              'automatic_promotion': False})
        if not fit(model, groups, anchors, root):
            update(phase='complete_no_accepted_update')
            return
        candidate = root/'candidate.pt'
        save_model(candidate, model, {'source': str(baseline), 'training': 'bounded-counterfactual-v1'})
        update(phase='fit_complete', candidate=str(candidate))
        if args.fit_only:
            return
        # Fixed training-only coverage, not selected using evaluation performance.
        selected = json.loads((source/'selected_cases.json').read_text())
        cases = [Path(x['path']) for x in selected[::4]][:8]
        original = migrate(baseline)
        update(phase='candidate_continuation_screen')
        def run(pair):
            i, case = pair
            return (continuation(case, root/'screen-baseline'/str(i), original),
                    continuation(case, root/'screen-candidate'/str(i), model))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            pairs = list(pool.map(run, enumerate(cases)))
        before, after = [x[0] for x in pairs], [x[1] for x in pairs]
        gate = screen_gate(before, after)
        write(root/'continuation-screen.json', {'baseline': before, 'candidate': after, 'gate': gate})
        update(screen=gate)
        if not gate['passed']:
            update(phase='rejected_by_continuation_screen')
            return
        seeds = config['evaluation_seeds'][:5]
        # Reuse exact same-seed, same-engine, same-starting-policy 2000-step baseline.
        old = [json.loads((source/'baseline-games'/f'episode-{i}.result.json').read_text()) for i in range(5)]
        if any(r['seed'] != str(seed) or r['model_sha256'] != sha(baseline) for r, seed in zip(old, seeds)):
            raise ValueError('baseline provenance mismatch')
        update(phase='paired_evaluation', evaluation_seeds=seeds, baseline=summary(old))
        new = play_batch(root/'candidate-games', candidate, seeds, False)
        write(root/'comparison.json', {'baseline': old, 'candidate': new})
        update(phase='complete', candidate_results=summary(new),
               warning='five previously inspected seeds are a regression screen, not fresh promotion evidence')
    except BaseException as exc:
        update(phase='failed', error=repr(exc))
        raise


if __name__ == '__main__':
    main()
