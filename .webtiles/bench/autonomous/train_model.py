"""Behavioral-cloning and small off-policy updates from JSONL replay."""
from __future__ import annotations

import argparse
import json
import random
import math
from pathlib import Path

import torch
from torch import nn

from model import ActionValueModel, save_model, tensor_for_actions


def _files(path: str | Path):
    path = Path(path)
    return sorted(path.glob("*.jsonl")) if path.is_dir() else [path]


def rows_from_replay(path: str | Path) -> list[dict]:
    rows = []
    for file in _files(path):
        result_path = file.with_suffix(".result.json")
        result = json.loads(result_path.read_text()) if result_path.exists() else {}
        with file.open() as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
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
    model = model or ActionValueModel()
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
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
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            total += float(loss.detach()); usable += 1
            epoch_usable += 1
        losses.append(total / max(1, epoch_usable))
    return model, {"rows": len(rows), "usable": usable, "epochs": epochs,
                   "losses": losses, "objective": "behavioral_cloning"}


def train_q_finetune(model: ActionValueModel, rows: list[dict], epochs: int = 1) -> dict:
    """Conservative score-to-go update; terminal score is the target."""
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-4, weight_decay=1e-5)
    usable, losses = 0, []
    for _ in range(epochs):
        total = 0.0
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
            prediction = model(tensor_for_actions(state, actions))[int(index)]
            loss = (prediction - target) ** 2
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            total += float(loss.detach()); usable += 1
        losses.append(total / max(1, usable))
    return {"usable": usable, "epochs": epochs, "losses": losses,
            "objective": "score_to_go_finetune"}


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
