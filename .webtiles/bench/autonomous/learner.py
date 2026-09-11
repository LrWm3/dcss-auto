"""Persistent, rejection-independent learner transactions and bounded replay."""
import json
import random
from pathlib import Path

from general_env import sha
from model import load_model, save_model
from train_model import train_behavioral_clone, train_q_finetune, train_counterfactual_preferences


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
    completed = sorted(folder.glob('cycle-*.ready.json'))
    completed = [p for p in completed if int(p.name.split('.')[0].split('-')[1]) < cycle]
    if completed:
        record = json.loads(completed[-1].read_text())
        parent = Path(record['path'])
        if sha(parent) != record['sha256']:
            raise ValueError('committed learner checkpoint changed')
    else:
        parent = Path(champion)
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
    anchors = balanced_sample(rows, 256, cycle)
    model, metadata = train_behavioral_clone(anchors, epochs=1, seed=cycle,
                                            model=model, optimizer_states=optimizers)
    metadata['ordinary_play_returns'] = train_q_finetune(
        model, balanced_sample(rows, 2048, cycle), optimizer_states=optimizers)
    metadata.update(parent=str(parent), parent_sha256=sha(parent),
                    optimizer_states=optimizers, learner_version='persistent-v1')
    save_model(candidate, model, metadata)
    return {k: v for k, v in metadata.items() if k != 'optimizer_states'}


def finish_candidate(root, cycle, candidate, rows):
    """Commit before evaluation: rejection never rolls learning back."""
    model, payload = load_model(candidate)
    metadata = payload['metadata']
    preferences = [r for r in rows if r.get('comparison_id') and r.get('return') is not None]
    # Bounded by retained replay; comparison_id prevents mixing continuation
    # policies/horizons into a false paired comparison.
    metadata['counterfactual_policy_update'] = train_counterfactual_preferences(
        model, preferences, anchors=balanced_sample(rows, 128, cycle),
        optimizer_states=metadata['optimizer_states'])
    save_model(candidate, model, metadata)
    record = {'path': str(candidate.resolve()), 'sha256': sha(candidate),
              'parent': metadata['parent'], 'train': {k: v for k, v in metadata.items() if k != 'optimizer_states'}}
    path = Path(root) / 'learner' / f'cycle-{cycle:04d}.ready.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, indent=2))
    temporary.replace(path)
    return record['train']
