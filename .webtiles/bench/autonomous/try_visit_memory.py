"""Bounded on-policy checkpoint collection -> counterfactuals -> fit -> screen.

No held-out checkpoint training, direction ban, or automatic promotion.
Uses native or explicitly enabled exploration score, never mixed units.
"""
import os
os.environ['DCSS_REPRESENTATION'] = 'spatial-v6'
os.environ['DCSS_HEALTH_FEATURES'] = '1'
os.environ['DCSS_REST_ONLY'] = '1'
os.environ['DCSS_VISIT_MEMORY'] = '1'
import argparse
import concurrent.futures
import gzip
import json
import math
import random
from pathlib import Path
import torch
from model import ActionValueModel, save_model, load_model, tensor_for_actions
from policy import Policy
from general_env import GeneralEnvironment, sha, ENGINE
from teacher import _actions
from bootstrap_repair import write, play_batch
from counterfactual import evaluate_checkpoint
from data_split import assert_training_seed, held_out_seed
from exploration_score import VERSION as EXPLORATION_VERSION, report_fields
from collection_sampling import capture_reason, select_snapshots
import storage


def migrate(path):
    payload = torch.load(path, map_location='cpu', weights_only=False)
    if payload['feature_version'] == 'general-features-v6-spatial-entities-health-v1-rest-v1-visits-v1':
        model, _ = load_model(path)
        objective = EXPLORATION_VERSION if os.environ.get('DCSS_EXPLORATION_SCORE') == '1' else None
        if payload.get('score_version') != objective:
            model.value_net.apply(lambda layer: layer.reset_parameters()
                                  if hasattr(layer, 'reset_parameters') else None)
        model.eval()
        return model
    assert payload['feature_version'] == 'general-features-v6-spatial-entities-health-v1-rest-v1'
    model = ActionValueModel(payload['hidden'])
    weights = payload['state_dict'].copy()
    for key in ('net.head.0.weight', 'value_net.head.0.weight'):
        old = weights[key]
        weights[key] = torch.cat((old, torch.zeros(old.shape[0], 8)), dim=1)
        assert weights[key].shape == model.state_dict()[key].shape
        x = torch.linspace(0, 1, old.shape[1])[None, :]
        torch.testing.assert_close(x @ old.T,
            torch.cat((x, torch.ones(1, 8)), dim=1) @ weights[key].T)
    model.load_state_dict(weights)
    model.eval()
    return model


def looping(s):
    memory = s.get('visit_memory') or {}
    history = s.get('history') or []
    actions = [h.get('action', {}) for h in history]
    moves = [(a.get('dx'), a.get('dy')) for a in actions]
    return (bool(s.get('safe')) and not s.get('monsters') and len(moves) == 4
            and all(a.get('kind') == 'MOVE' for a in actions)
            and moves[0] == moves[2] and moves[1] == moves[3]
            and moves[0] == tuple(-v for v in moves[1])
            and memory.get('since_discovery', 0) >= 24
            and memory.get('since_new_tile', 0) >= 24)


def collect(root, model, seed, budget=600):
    assert_training_seed(seed)
    env = GeneralEnvironment(root / 'actor', seed=str(seed), data_role='training')
    env.record_events = False
    policy = Policy(model, epsilon=0)
    anchors = []
    case = None
    snapshots = []
    decisions = 0
    try:
        s = env.reset()
        for step in range(budget):
            if s.get('terminal'):
                break
            loop = looping(s)
            reason = capture_reason(s, step,
                ordinary_saved=any(c['reason'] == 'ordinary_exploration' for c in snapshots), loop=loop)
            if reason:
                case = root / f'checkpoint-{step:04d}'
                env.save_state(case)
                snapshots.append({'path': str(case), 'step': step, 'reason': reason,
                                  'level': s.get('level'), 'score': s.get('score'),
                                  **report_fields(s)})
            if loop:
                break
            if step % 12 == 0 and len(anchors) < 32:
                anchors.append(s)
            s = env.step(policy.choose(s)[0])
            decisions += 1
        with gzip.open(root / 'anchors.json.gz', 'wt') as stream:
            json.dump(anchors, stream)
        selected = select_snapshots(snapshots, s.get('terminal'), decisions)
        result = {'seed': str(seed), 'steps': decisions, 'case': str(case) if case else None,
                  'cases': selected, 'snapshots': snapshots,
                  **report_fields(s),
                  'score': s.get('score'), 'level': s.get('level'),
                  'terminal': s.get('terminal'), 'memory': s.get('visit_memory')}
        write(root / 'result.json', result)
        return result
    except Exception as exc:
        result = {'seed': str(seed), 'case': None, 'cases': [], 'error': repr(exc)}
        write(root / 'result.json', result)
        return result
    finally:
        env.close()
        storage.finish_logs(env.works)


def determinism(case, root, model):
    sequences = []
    for repeat in range(2):
        env = GeneralEnvironment(root / str(repeat), data_role='diagnostic')
        env.record_events = False
        try:
            s = env.reset(case)
            saved = json.loads((case / 'case.json').read_text())['observation']
            assert s['visit_memory'] == saved['visit_memory']
            sequence = []
            for _ in range(8):
                if s.get('terminal'):
                    break
                s = env.step(Policy(model, epsilon=0).choose(s)[0])
                sequence.append(s)
            sequences.append(sequence)
        finally:
            env.close()
            storage.finish_logs(env.works)
    assert sequences[0] == sequences[1], 'restored continuation diverged'
    write(root / 'result.json', {'passed': True, 'steps': len(sequences[0]),
          'compared': 'complete structured observations including visit memory'})


from conservative_ranking import ranking_groups, bounded_fit


def fit(model, groups, anchors, root, epochs=8):
    result = bounded_fit(model, groups, anchors, epochs)
    write(root / 'training.json', result)
    return result['trained']


def summary(results):
    valid = all('error' not in r and isinstance(r.get('score'), (int, float))
                and math.isfinite(r['score']) for r in results)
    return {'mean_score': sum(r['score'] for r in results)/len(results) if valid and results else None,
            'mean_native_score': sum(r['score'] for r in results)/len(results) if valid and results else None,
            'mean_training_score': sum(r['training_score'] for r in results)/len(results)
                if valid and results and all(r.get('training_score') is not None for r in results) else None,
            'scores': [r.get('score') for r in results],
            'descents': sum(r.get('action_counts', {}).get('TAKE_STAIRS_DOWN', 0) > 0 for r in results),
            'deaths': sum(r.get('terminal_kind') == 'death' for r in results),
            'cutoffs': sum(bool(r.get('truncated')) for r in results),
            'errors': sum('error' in r for r in results)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--initial', type=Path, required=True)
    parser.add_argument('--smoke-only', action='store_true')
    parser.add_argument('--seed-start', type=int, default=60917000)
    parser.add_argument('--training-seeds', type=int, default=8)
    parser.add_argument('--evaluation-count', type=int, default=5)
    parser.add_argument('--evaluation-seed-start', type=int, default=16140901064556770664)
    args = parser.parse_args()
    if args.training_seeds < 1 or args.evaluation_count < 1:
        parser.error('seed counts must be positive')
    eval_seeds = [str(args.evaluation_seed_start+i) for i in range(args.evaluation_count)]
    if not all(held_out_seed(s) for s in eval_seeds):
        parser.error('evaluation seeds must use the reserved held-out namespace')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    storage.configure(root)
    torch.set_num_threads(1)
    torch.manual_seed(17)
    status = {'phase': 'collection', 'promoted': False}
    def update(**values):
        status.update(values)
        write(root / 'latest_status.json', status)
    try:
        model = migrate(args.initial)
        baseline = root / 'initial.pt'
        save_model(baseline, model, {'source': str(args.initial.resolve()),
            'initialization': 'existing visit policy retained, or explicit zero-column REST migration; critic reset when objective changes'})
        seeds = [args.seed_start + i for i in range(min(4,args.training_seeds) if args.smoke_only else args.training_seeds)]
        for seed in seeds:
            assert_training_seed(seed)
        write(root/'config.json', {'initial': str(args.initial.resolve()), 'initial_sha256': sha(args.initial),
              'engine': str(ENGINE), 'engine_sha256': sha(ENGINE), 'training_seeds': seeds,
              'evaluation_seeds': eval_seeds, 'score_version': EXPLORATION_VERSION
                  if os.environ.get('DCSS_EXPLORATION_SCORE') == '1' else None,
              'collection_budget': 600, 'continuations': 3, 'continuation_steps': 384,
              'collection_protocol': 'ordinary-periodic-predeath-v2', 'max_selected_cases_per_seed': 2,
              'evaluation_decision_limit': 2000, 'automatic_promotion': False})
        update(training_seeds=seeds, collection_budget=600,
               starting_policy=str(args.initial.resolve()), evaluation_seeds=eval_seeds,
               score_version=EXPLORATION_VERSION if os.environ.get('DCSS_EXPLORATION_SCORE') == '1' else None,
               continuations=3, continuation_steps=384)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            collected = list(pool.map(lambda seed: collect(root / 'collection' / str(seed), model, seed), seeds))
        write(root / 'collection.json', collected)
        selections = [case for r in collected for case in r.get('cases', [])]
        cases = [Path(case['path']) for case in selections]
        write(root/'selected_cases.json', selections)
        if not cases:
            update(phase='no_checkpoints_captured')
            return
        update(phase='restore_smoke', captured_cases=len(cases),
               captured_loops=sum(c['reason'] == 'loop' for c in selections),
               preceding_death_cases=sum(c.get('selection_reason') == 'preceding_death' for c in selections))
        determinism(cases[0], root / 'determinism', model)
        if args.smoke_only:
            update(phase='smoke_complete')
            return
        groups = []
        update(phase='counterfactuals', completed_cases=0)
        for i, case in enumerate(cases):
            rows = evaluate_checkpoint(case, root / 'branches' / str(i), baseline,
                  top_k=3, random_k=2, continuations=3, continuation_steps=384,
                  max_workers=6, include_teacher=True)
            with gzip.open(root / f'counterfactual-{i}.json.gz', 'wt') as stream:
                json.dump(rows, stream)
            groups.append(rows)
            update(completed_cases=i+1, informative_states=len(ranking_groups(groups)))
        anchors = []
        for seed in seeds:
            path = root / 'collection' / str(seed) / 'anchors.json.gz'
            if not path.exists():
                continue
            with gzip.open(path, 'rt') as stream:
                anchors.extend(json.load(stream))
        random.Random(17).shuffle(anchors)
        update(phase='training')
        trained = fit(model, groups, anchors, root)
        if not trained:
            update(phase='complete_no_score_signal', trained=False)
            return
        candidate = root / 'candidate.pt'
        save_model(candidate, model, {'source': str(baseline), 'training': 'score-counterfactual-visits-v1'})
        # A first-action label assumes the old continuation policy. Check the
        # actual updated policy repeatedly acting before any held-out screen.
        from retry_exploration_fit import continuation, screen_gate
        original = migrate(baseline)
        screen_cases = cases[::max(1, len(cases)//8)][:8]
        update(phase='candidate_continuation_screen')
        def screen(pair):
            i, case = pair
            return (continuation(case, root/'screen-baseline'/str(i), original),
                    continuation(case, root/'screen-candidate'/str(i), model))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            screens = list(pool.map(screen, enumerate(screen_cases)))
        screen_before, screen_after = [s[0] for s in screens], [s[1] for s in screens]
        gate = screen_gate(screen_before, screen_after)
        write(root/'continuation-screen.json', {'baseline': screen_before,
              'candidate': screen_after, 'gate': gate})
        update(screen=gate)
        if not gate['passed']:
            update(phase='rejected_by_continuation_screen')
            return
        update(phase='baseline_evaluation', evaluation_seeds=eval_seeds)
        before = play_batch(root / 'baseline-games', baseline, eval_seeds, False)
        update(phase='candidate_evaluation', baseline=summary(before))
        after = play_batch(root / 'candidate-games', candidate, eval_seeds, False)
        old_mean, new_mean = summary(before)['mean_score'], summary(after)['mean_score']
        update(phase='complete', candidate=summary(after), trained=True,
               mean_score_delta=new_mean-old_mean if old_mean is not None and new_mean is not None else None)
    except BaseException as exc:
        update(phase='failed', error=repr(exc))
        raise


if __name__ == '__main__':
    main()
