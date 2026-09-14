"""Behavioral-cloning and small off-policy updates from JSONL replay."""
from __future__ import annotations

import argparse
import json
import random
import math
import copy
import hashlib
from pathlib import Path
from collections import OrderedDict

import torch
from torch import nn

from model import ActionValueModel, save_model, tensor_for_actions
import storage
import os
from exploration_score import learning_score, VERSION as EXPLORATION_VERSION
from data_split import assert_training_seed
from score_result import has_episode_score

N_STEP_HORIZON = 3
N_STEP_GAMMA = 0.995
RETURN_POLICY_LR = 2e-4
RETURN_POLICY_MAX_KL = 0.01


def _files(path: str | Path):
    path = Path(path)
    return storage.replay_files(path) if path.is_dir() else [path]


def _log_score(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return math.log1p(value) if math.isfinite(value) and value >= 0 else None


def _annotate_n_step(rows, result, horizon=N_STEP_HORIZON, gamma=N_STEP_GAMMA):
    """Attach short-horizon score-difference targets without rewriting replay.

    Crawl exposes a live official score, so each decision gets a local score
    delta plus a bootstrap state. Terminal rows use the final official score.
    The fields are derived in memory for compatibility with old replay shards.
    """
    final_score = learning_score(result)
    for start, row in enumerate(rows):
        reward, discount, next_state = 0.0, 1.0, None
        terminal, used, score_observed = False, 0, False
        for offset in range(horizon):
            index = start + offset
            if index >= len(rows):
                break
            item = rows[index]
            exploration = result.get('score_version') == EXPLORATION_VERSION
            before = item.get("training_score_before" if exploration else "score_before")
            if before is None:
                observation = item.get("observation") or {}
                before = learning_score(observation) if observation.get("score_status") == "live_official" else None
            after = item.get("training_score_after" if exploration else "score_after")
            candidate_next = item.get("next_observation") or {}
            if after is None:
                after = learning_score(candidate_next) if candidate_next.get("score_status") == "live_official" else None
            before = _log_score(before)
            after = _log_score(after)
            if item.get("terminal"):
                terminal_score = item.get("return")
                if terminal_score is None:
                    terminal_score = final_score
                after = _log_score(terminal_score)
            if before is not None and after is not None:
                reward += discount * (after - before)
                score_observed = True
            next_state = item.get("next_observation")
            used += 1
            if item.get("terminal") or (next_state and next_state.get("terminal")):
                terminal = True
                break
            discount *= gamma
        row["n_step_reward"] = reward
        row["n_step_discount"] = discount
        row["n_step_terminal"] = terminal
        row["n_step_steps"] = used
        row["n_step_score_observed"] = score_observed
        row["n_step_next_observation"] = next_state


def _td_target(reference, row, feature_cache):
    """Return an action-level target, falling back to historical final scores."""
    terminal = row.get("n_step_terminal")
    if terminal:
        score = row.get("return")
        return _log_score(score)
    next_state = row.get("n_step_next_observation") or row.get("next_observation")
    actions = _actions(next_state or {})
    if next_state and actions and row.get("n_step_steps") and row.get("n_step_score_observed"):
        with torch.no_grad():
            next_values = reference.value(feature_cache.get(next_state))
            continuation = float(next_values.max().detach())
        return float(row.get("n_step_reward", 0.0)) + float(
            row.get("n_step_discount", N_STEP_GAMMA)) * continuation
    return _log_score(row.get("return"))


def rows_from_replay(path: str | Path) -> list[dict]:
    rows = []
    for file in _files(path):
        result_path = storage.result_path(file)
        # Interrupted episodes are forensic artifacts, not complete replay.
        if file.name != "counterfactual.jsonl" and not result_path.exists():
            continue
        result = json.loads(result_path.read_text()) if result_path.exists() else {}
        if result.get("data_role", "training") != "training":
            continue
        assert_training_seed(result.get("seed"))
        expected_score_version = EXPLORATION_VERSION if os.environ.get('DCSS_EXPLORATION_SCORE') == '1' else None
        if result.get('score_version') != expected_score_version:
            continue  # Never mix native and scaled exploration return units.
        file_rows = []
        with storage.open_text(file) as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("data_role", "training") != "training":
                    continue
                assert_training_seed(row.get("episode_seed", row.get("source_seed")))
                state = row.get("observation")
                if (row.get("type") == "transition" or state) and isinstance(state, dict):
                    if state.get("schema") == "crawl-general-v1":
                        if has_episode_score(result):
                            row["return"] = learning_score(result)
                        # Historical branch shards already identify their
                        # frozen cycle policy. State hashing further separates
                        # distinct probes; do not discard their useful labels.
                        if str(row.get('policy_version', '')).endswith(':counterfactual'):
                            row.setdefault('comparison_id', 'legacy:' + row['policy_version'])
                        file_rows.append(row)
        _annotate_n_step(file_rows, result)
        rows.extend(file_rows)
    return rows


def _actions(state):
    actions = state.get("actions", [])
    if isinstance(actions, dict):
        return [actions[key] for key in sorted(actions, key=lambda x: int(x))]
    return list(actions)


class FeatureCache:
    """Bounded training-only cache; replay observations must remain immutable."""
    def __init__(self, limit=4096):
        from features import FEATURE_VERSION
        self.limit = min(limit, 128) if FEATURE_VERSION.startswith('general-features-v6-spatial-entities') else limit
        self.entries = OrderedDict()

    def get(self, state):
        key = id(state)
        if key not in self.entries:
            self.entries[key] = (state, tensor_for_actions(state, _actions(state)))
            if len(self.entries) > self.limit:
                self.entries.popitem(last=False)
        self.entries.move_to_end(key)
        return self.entries[key][1]


def train_behavioral_clone(rows: list[dict], epochs: int = 3,
                           seed: int = 0, model=None, optimizer_states=None, feature_cache=None) -> tuple[ActionValueModel, dict]:
    if not rows:
        raise ValueError("replay contains no usable transitions")
    random.seed(seed)
    torch.manual_seed(seed)
    reference = copy.deepcopy(model).eval() if model is not None else None
    model = model or ActionValueModel()
    optimizer = torch.optim.AdamW(model.net.parameters(),
                                 lr=2e-4 if reference is not None else 2e-3, weight_decay=1e-4)
    if optimizer_states is not None and 'bc' in optimizer_states:
        optimizer.load_state_dict(optimizer_states['bc'])
    losses, usable = [], 0
    feature_cache = feature_cache if feature_cache is not None else FeatureCache()
    priors = {}
    for _ in range(epochs):
        order = list(range(len(rows)))
        random.shuffle(order)
        total = 0.0
        epoch_usable = 0
        for row_index in order:
            row = rows[row_index]
            state = row["observation"]
            actions = _actions(state)
            chosen = row.get("action")
            target = row.get("teacher_action_index")
            if target is None and row.get("policy_version") in ("teacher", "bootstrap"):
                target = row.get("action_index")
            if target is None:
                continue
            if not 0 <= int(target) < len(actions):
                continue
            features = feature_cache.get(state)
            scores = model(features).unsqueeze(0)
            loss = nn.functional.cross_entropy(scores, torch.tensor([int(target)]))
            if reference is not None:
                if row_index not in priors:
                    with torch.no_grad():
                        priors[row_index] = reference(features).softmax(dim=-1)
                prior = priors[row_index]
                loss = loss + 2.0 * nn.functional.kl_div(
                    scores.log_softmax(dim=-1), prior.unsqueeze(0), reduction="batchmean")
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            total += float(loss.detach()); usable += 1
            epoch_usable += 1
        losses.append(total / max(1, epoch_usable))
    if optimizer_states is not None:
        optimizer_states['bc'] = optimizer.state_dict()
    return model, {"rows": len(rows), "usable": usable, "epochs": epochs,
                   "losses": losses, "objective": "behavioral_cloning"}


def train_q_finetune(model: ActionValueModel, rows: list[dict], epochs: int = 1, optimizer_states=None, feature_cache=None) -> dict:
    """Fit an independent short-horizon score critic; cannot alter policy logits."""
    optimizer = torch.optim.AdamW(model.value_net.parameters(), lr=5e-4, weight_decay=1e-5)
    if optimizer_states is not None and 'critic' in optimizer_states:
        optimizer.load_state_dict(optimizer_states['critic'])
    usable, losses = 0, []
    feature_cache = feature_cache if feature_cache is not None else FeatureCache()
    reference = copy.deepcopy(model).eval()
    target_kinds = {"n_step": 0, "terminal_score": 0, "legacy_score": 0}
    for _ in range(epochs):
        total = 0.0
        epoch_usable = 0
        for row in rows:
            state, actions = row.get("observation"), _actions(row.get("observation", {}))
            if not actions:
                continue
            index = row.get("action_index")
            if index is None:
                index = next((i for i, a in enumerate(actions) if a == row.get("action")), -1)
            if not 0 <= int(index) < len(actions):
                continue
            target = _td_target(reference, row, feature_cache)
            if target is None:
                continue
            if row.get("n_step_steps") and row.get("n_step_score_observed"):
                target_kinds["n_step" if not row.get("n_step_terminal") else "terminal_score"] += 1
            else:
                target_kinds["legacy_score"] += 1
            prediction = model.value(feature_cache.get(state))[int(index)]
            loss = nn.functional.smooth_l1_loss(prediction, prediction.new_tensor(target))
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            total += float(loss.detach()); usable += 1; epoch_usable += 1
        losses.append(total / max(1, epoch_usable))
    if optimizer_states is not None:
        optimizer_states['critic'] = optimizer.state_dict()
    return {"usable": usable, "epochs": epochs, "losses": losses,
            "objective": "independent_n_step_score_critic",
            "target_kinds": target_kinds, "horizon": N_STEP_HORIZON,
            "gamma": N_STEP_GAMMA}


def train_return_policy(model, rows, optimizer_states=None, epochs=3, feature_cache=None):
    """Bounded off-policy score-advantage update with a frozen reference.

    Only scored ordinary trajectories with logged sampling probabilities enter.
    The critic supplies a baseline; actual logged game returns supply the target.
    A full-batch KL guard rolls back a proposed step (including Adam state) if
    the mean policy KL exceeds .01. Teacher labels are not optimization targets.
    """
    feature_cache = feature_cache if feature_cache is not None else FeatureCache()
    reference = copy.deepcopy(model).eval()
    optimizer = torch.optim.AdamW(model.net.parameters(), lr=RETURN_POLICY_LR, weight_decay=0)
    if optimizer_states is not None and 'actor_return' in optimizer_states:
        optimizer.load_state_dict(optimizer_states['actor_return'])
    encoded = []
    target_kinds = {"n_step": 0, "terminal_score": 0, "legacy_score": 0}
    advantages = []
    for row in rows:
        probability = row.get('behavior_probability')
        actions = _actions(row.get('observation', {}))
        i = row.get('action_index', -1)
        if (row.get('comparison_id') or probability is None
                or not 0 < probability <= 1 or not 0 <= i < len(actions)):
            continue
        x = feature_cache.get(row['observation'])
        with torch.no_grad():
            prior = reference(x).softmax(-1)
            baseline = (prior * reference.value(x)).sum()
            target = _td_target(reference, row, feature_cache)
            if target is None:
                continue
            advantage = (target - baseline).clamp(-2, 2)
        if row.get("n_step_steps") and row.get("n_step_score_observed"):
            target_kinds["terminal_score" if row.get("n_step_terminal") else "n_step"] += 1
        else:
            target_kinds["legacy_score"] += 1
        advantages.append(float(advantage))
        encoded.append((x, i, probability, prior, advantage))
    if not encoded:
        return {'usable':0, 'updates':0, 'reason':'no scored trajectories with behavior probabilities'}
    updates = 0
    for _ in range(epochs):
        weights, opt = copy.deepcopy(model.net.state_dict()), copy.deepcopy(optimizer.state_dict())
        optimizer.zero_grad()
        for x, i, behavior, prior, advantage in encoded:
            logp = model(x).log_softmax(-1)
            ratio = (logp[i].detach().exp() / behavior).clamp(max=5)
            loss = -ratio * advantage * logp[i]
            loss += 2 * nn.functional.kl_div(logp, prior, reduction='sum')
            (loss / len(encoded)).backward()
        nn.utils.clip_grad_norm_(model.net.parameters(), 1)
        optimizer.step()
        with torch.no_grad():
            kl = sum(float(nn.functional.kl_div(model(x).log_softmax(-1), prior, reduction='sum'))
                     for x, _, _, prior, _ in encoded) / len(encoded)
        if not math.isfinite(kl) or kl > RETURN_POLICY_MAX_KL:
            model.net.load_state_dict(weights); optimizer.load_state_dict(opt)
            break
        updates += 1
    if optimizer_states is not None:
        optimizer_states['actor_return'] = optimizer.state_dict()
    with torch.no_grad():
        final_kl = sum(float(nn.functional.kl_div(model(x).log_softmax(-1), prior, reduction='sum'))
                       for x, _, _, prior, _ in encoded) / len(encoded)
    return {'usable':len(encoded), 'updates':updates, 'mean_reference_kl':final_kl,
            'objective':'clipped_score_advantage_with_kl',
            'positive_advantages':sum(float(e[4])>0 for e in encoded),
            'negative_advantages':sum(float(e[4])<0 for e in encoded),
            'mean_abs_advantage':sum(abs(x) for x in advantages) / max(1, len(advantages)),
            'target_kinds': target_kinds, 'horizon': N_STEP_HORIZON,
            'learning_rate': RETURN_POLICY_LR, 'max_kl': RETURN_POLICY_MAX_KL}


def train_counterfactual_preferences(model, rows, anchors=(), epochs=20, optimizer_states=None, feature_cache=None):
    """Small policy updates from paired-state empirical return comparisons.

    An isolated good/bad absolute return is not an action preference.
    Failed continuations and ties provide no ranking label. Official fixed-horizon
    scores are valid comparisons within their own protocol. Replay KL limits drift.
    """
    feature_cache = feature_cache if feature_cache is not None else FeatureCache()
    groups = {}
    for row in rows:
        if row.get("return") is None:
            continue
        state = row["observation"]
        key = (row.get('comparison_id'), hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest())
        groups.setdefault(key, []).append(row)
    pairs = []
    for group in groups.values():
        best, worst = max(group, key=lambda r: r["return"]), min(group, key=lambda r: r["return"])
        if best["return"] <= worst["return"] or best["action_index"] == worst["action_index"]:
            continue
        state = best["observation"]
        pairs.append((feature_cache.get(state),
                      int(best["action_index"]), int(worst["action_index"])))
    if not pairs:
        return {"pairs": 0, "updates": 0, "reason": "no paired unequal completed returns"}
    reference = copy.deepcopy(model).eval()
    rng = random.Random(73)
    sample = rng.sample(list(anchors), min(128, len(anchors)))
    encoded = [feature_cache.get(r["observation"])
               for r in sample if _actions(r["observation"])]
    optimizer = torch.optim.AdamW(model.net.parameters(), lr=1e-4, weight_decay=0)
    if optimizer_states is not None and 'preferences' in optimizer_states:
        optimizer.load_state_dict(optimizer_states['preferences'])
    def margin(pair):
        features, best, worst = pair
        with torch.no_grad():
            scores = model(features)
            return float(scores[best]-scores[worst])
    before = [margin(p) for p in pairs]
    with torch.no_grad():
        priors = {id(x):reference(x).softmax(-1) for x in encoded + [p[0] for p in pairs]}
    for _ in range(epochs):
        for features, best, worst in pairs:
            scores = model(features)
            loss = nn.functional.softplus(scores[worst]-scores[best])
            batch = [features] + rng.sample(encoded, min(8, len(encoded)))
            for x in batch:
                prior = priors[id(x)]
                loss = loss + 10.0 / len(batch) * nn.functional.kl_div(
                    model(x).log_softmax(-1).unsqueeze(0), prior.unsqueeze(0), reduction="batchmean")
            optimizer.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(model.net.parameters(), 1.0)
            optimizer.step()
    if optimizer_states is not None:
        optimizer_states['preferences'] = optimizer.state_dict()
    return {"pairs": len(pairs), "updates": epochs * len(pairs),
            "margins_before": before, "margins_after": [margin(p) for p in pairs],
            "objective": "paired_empirical_return_preferences_with_replay_kl"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("replay", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--epochs", type=int, default=3)
    args = parser.parse_args()
    rows = rows_from_replay(args.replay)
    model, metadata = train_behavioral_clone(rows, args.epochs)
    save_model(args.output, model, metadata)
    print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
