"""Persistent, rejection-independent learner transactions and bounded replay."""
import json
import os
import random
from pathlib import Path
import torch

from general_env import sha
from model import load_model, save_model
from train_model import train_return_policy, train_q_finetune, train_counterfactual_preferences, FeatureCache

LINEAGE_POLICY = "champion-reset-on-rejection-v1"


def distribution_diagnostics(old_logits, new_logits):
    """KL/entropy in log space: finite confident logits must not yield 0*inf."""
    if not (torch.isfinite(old_logits).all() and torch.isfinite(new_logits).all()):
        raise ValueError('Non-finite policy logits in diagnostics')
    logp = old_logits.double().log_softmax(-1)
    logq = new_logits.double().log_softmax(-1)
    return (float((logp.exp() * (logp-logq)).sum()),
            float(-(logq.exp() * logq).sum()))


def policy_diagnostics(parent, candidate, rows, limit=256):
    """Measure whether a candidate actually changes decisions."""
    old, _ = load_model(parent)
    new, _ = load_model(candidate)
    records = []
    for row in rows:
        state = row.get('observation', {})
        actions = state.get('actions', [])
        if isinstance(actions, dict):
            actions = [actions[key] for key in sorted(actions, key=lambda x: int(x))]
        if not actions:
            continue
        records.append((state, actions))
        if len(records) >= limit:
            break
    if not records:
        return {'rows': 0, 'mean_kl': 0.0, 'changed_action_fraction': 0.0,
                'mean_entropy': 0.0}
    from model import tensor_for_actions
    total_kl = changed = entropy = 0.0
    for state, actions in records:
        features = tensor_for_actions(state, actions)
        with torch.no_grad():
            p = old(features)
            q = new(features)
            kl, ent = distribution_diagnostics(p, q)
            total_kl += kl
            changed += float(int(p.argmax() != q.argmax()))
            entropy += ent
    n = len(records)
    return {'rows': n, 'mean_kl': total_kl / n,
            'changed_action_fraction': changed / n, 'mean_entropy': entropy / n}


def parent_for_cycle(root, cycle, champion):
    """Freeze the actor/learner parent before collecting any episode."""
    folder = Path(root) / 'learner'
    folder.mkdir(exist_ok=True)
    path = folder / f'cycle-{cycle:04d}.parent.json'
    if path.exists():
        record = json.loads(path.read_text())
        parent = Path(record['path'])
        if sha(parent) != record['sha256']:
            raise ValueError('frozen learner parent changed')
        return parent
    # A rejected exploratory candidate must not silently become the parent of
    # the next official candidate. Promoted candidates are copied into the
    # champions directory, so latest_champion is the durable promotion gate.
    parent = Path(champion)
    champions = sorted((Path(root) / 'champions').glob('V*.pt'),
                       key=lambda p: int(p.stem[1:]))
    if champions:
        parent = champions[-1]
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'path': str(parent.resolve()), 'sha256': sha(parent)}))
    temporary.replace(path)
    return parent


def balanced_sample(rows, limit, seed):
    """Round-robin shuffled seeds, preventing long/stalled games dominating."""
    rng = random.Random(seed)
    groups = {}
    for row in rows:
        groups.setdefault(str(row.get('episode_seed', row.get('source_seed', 'unknown'))), []).append(row)
    for group in groups.values():
        rng.shuffle(group)
    result = []
    while groups and len(result) < limit:
        keys = list(groups)
        rng.shuffle(keys)
        for key in keys:
            result.append(groups[key].pop())
            if not groups[key]:
                del groups[key]
            if len(result) == limit:
                break
    return result


def prepare_candidate(parent, candidate, rows, cycle):
    model, payload = load_model(parent)
    optimizers = payload.get('metadata', {}).get('optimizer_states', {})
    from exploration_score import VERSION
    objective = VERSION if os.environ.get('DCSS_EXPLORATION_SCORE') == '1' else None
    reset_critic = payload.get('score_version') != objective
    if reset_critic:
        # Policy can bootstrap across objectives; critic/optimizer return units cannot.
        torch.manual_seed(cycle)
        model.value_net.apply(lambda layer: layer.reset_parameters()
                              if hasattr(layer, 'reset_parameters') else None)
        optimizers = {}
    features = FeatureCache()
    metadata = {'ordinary_play_returns': train_q_finetune(
        model, balanced_sample(rows, 2048, cycle), optimizer_states=optimizers, feature_cache=features)
    }
    eligible = [r for r in rows if r.get('behavior_probability') is not None and not r.get('comparison_id')]
    metadata['score_policy_update'] = train_return_policy(model, balanced_sample(eligible, 256, cycle),
            optimizer_states=optimizers, feature_cache=features)
    metadata.update(parent=str(parent), parent_sha256=sha(parent),
                    score_version=objective, critic_reset_for_objective=reset_critic,
                    optimizer_states=optimizers, learner_version='score-policy-v2',
                    lineage_policy=LINEAGE_POLICY)
    save_model(candidate, model, metadata)
    return {k: v for k, v in metadata.items() if k != 'optimizer_states'}


def finish_candidate(root, cycle, candidate, rows):
    """Commit before evaluation: rejection never rolls learning back."""
    model, payload = load_model(candidate)
    metadata = payload['metadata']
    preferences = [r for r in rows if r.get('comparison_id') and r.get('return') is not None
                   and r.get('return_protocol') == (
                       'exploration_score_at_terminal_or_fixed_horizon_v1'
                       if os.environ.get('DCSS_EXPLORATION_SCORE') == '1' else
                       'official_score_at_terminal_or_fixed_horizon_v2')]
    # Bounded by retained replay; comparison_id prevents mixing continuation
    # policies/horizons into a false paired comparison.
    metadata['counterfactual_policy_update'] = train_counterfactual_preferences(
        model, preferences, anchors=balanced_sample(rows, 128, cycle),
        optimizer_states=metadata['optimizer_states'])
    save_model(candidate, model, metadata)
    metadata['policy_diagnostics'] = policy_diagnostics(
        metadata['parent'], candidate, balanced_sample(rows, 256, cycle))
    save_model(candidate, model, metadata)
    record = {'path': str(candidate.resolve()), 'sha256': sha(candidate),
              'parent': metadata['parent'], 'train': {k: v for k, v in metadata.items() if k != 'optimizer_states'}}
    path = Path(root) / 'learner' / f'cycle-{cycle:04d}.ready.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, indent=2))
    temporary.replace(path)
    return record['train']
