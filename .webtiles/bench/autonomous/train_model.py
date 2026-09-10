"""Behavioral-cloning and small off-policy updates from JSONL replay."""
from __future__ import annotations

import argparse
import json
import random
import math
import copy
import hashlib
from pathlib import Path

import torch
from torch import nn

from model import ActionValueModel, save_model, tensor_for_actions
import storage
from data_split import assert_training_seed


def _files(path: str | Path):
    path = Path(path)
    return storage.replay_files(path) if path.is_dir() else [path]


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
                        if result.get("terminal") and result.get("score") is not None:
                            row["return"] = result["score"]
                        rows.append(row)
    return rows


def _actions(state):
    actions = state.get("actions", [])
    if isinstance(actions, dict):
        return [actions[key] for key in sorted(actions, key=lambda x: int(x))]
    return list(actions)


def train_behavioral_clone(rows: list[dict], epochs: int = 3,
                           seed: int = 0, model=None) -> tuple[ActionValueModel, dict]:
    if not rows:
        raise ValueError("replay contains no usable transitions")
    random.seed(seed)
    torch.manual_seed(seed)
    reference = copy.deepcopy(model).eval() if model is not None else None
    model = model or ActionValueModel()
    optimizer = torch.optim.AdamW(model.net.parameters(),
                                 lr=2e-4 if reference is not None else 2e-3, weight_decay=1e-4)
    losses, usable = [], 0
    encoded = {}
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
            if row_index not in encoded:
                encoded[row_index] = tensor_for_actions(state, actions)
            scores = model(encoded[row_index]).unsqueeze(0)
            loss = nn.functional.cross_entropy(scores, torch.tensor([int(target)]))
            if reference is not None:
                with torch.no_grad():
                    prior = reference(encoded[row_index]).softmax(dim=-1)
                loss = loss + 2.0 * nn.functional.kl_div(
                    scores.log_softmax(dim=-1), prior.unsqueeze(0), reduction="batchmean")
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            total += float(loss.detach()); usable += 1
            epoch_usable += 1
        losses.append(total / max(1, epoch_usable))
    return model, {"rows": len(rows), "usable": usable, "epochs": epochs,
                   "losses": losses, "objective": "behavioral_cloning"}


def train_q_finetune(model: ActionValueModel, rows: list[dict], epochs: int = 1) -> dict:
    """Fit an independent return critic; cannot alter policy logits."""
    optimizer = torch.optim.AdamW(model.value_net.parameters(), lr=5e-4, weight_decay=1e-5)
    usable, losses = 0, []
    for _ in range(epochs):
        total = 0.0
        epoch_usable = 0
        for row in rows:
            if row.get("return") is None:
                continue
            state, actions = row.get("observation"), _actions(row.get("observation", {}))
            if not actions:
                continue
            index = row.get("action_index")
            if index is None:
                index = next((i for i, a in enumerate(actions) if a == row.get("action")), -1)
            if not 0 <= int(index) < len(actions):
                continue
            target = math.log1p(max(0.0, float(row["return"])))
            prediction = model.value(tensor_for_actions(state, actions))[int(index)]
            loss = (prediction - target) ** 2
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            total += float(loss.detach()); usable += 1; epoch_usable += 1
        losses.append(total / max(1, epoch_usable))
    return {"usable": usable, "epochs": epochs, "losses": losses,
            "objective": "independent_score_critic"}


def train_counterfactual_preferences(model, rows, anchors=(), epochs=20):
    """Small policy updates from paired-state empirical return comparisons.

    An isolated good/bad absolute return is not an action preference. Truncated
    continuations and ties provide no ranking label. Replay KL limits drift.
    """
    groups = {}
    for row in rows:
        if row.get("return") is None:
            continue
        state = row["observation"]
        key = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
        groups.setdefault(key, []).append(row)
    pairs = []
    for group in groups.values():
        best, worst = max(group, key=lambda r: r["return"]), min(group, key=lambda r: r["return"])
        if best["return"] <= worst["return"] or best["action_index"] == worst["action_index"]:
            continue
        state = best["observation"]
        pairs.append((tensor_for_actions(state, _actions(state)),
                      int(best["action_index"]), int(worst["action_index"])))
    if not pairs:
        return {"pairs": 0, "updates": 0, "reason": "no paired unequal completed returns"}
    reference = copy.deepcopy(model).eval()
    rng = random.Random(73)
    sample = rng.sample(list(anchors), min(128, len(anchors)))
    encoded = [tensor_for_actions(r["observation"], _actions(r["observation"]))
               for r in sample if _actions(r["observation"])]
    optimizer = torch.optim.AdamW(model.net.parameters(), lr=1e-4, weight_decay=0)
    def margin(pair):
        features, best, worst = pair
        with torch.no_grad():
            scores = model(features)
            return float(scores[best]-scores[worst])
    before = [margin(p) for p in pairs]
    for _ in range(epochs):
        for features, best, worst in pairs:
            scores = model(features)
            loss = nn.functional.softplus(scores[worst]-scores[best])
            batch = [features] + rng.sample(encoded, min(8, len(encoded)))
            for x in batch:
                with torch.no_grad():
                    prior = reference(x).softmax(-1)
                loss = loss + 10.0 / len(batch) * nn.functional.kl_div(
                    model(x).log_softmax(-1).unsqueeze(0), prior.unsqueeze(0), reduction="batchmean")
            optimizer.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(model.net.parameters(), 1.0)
            optimizer.step()
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
