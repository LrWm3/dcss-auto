"""Behavioral-cloning and small off-policy updates from JSONL replay."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import torch
from torch import nn

from model import ActionValueModel, save_model, tensor_for_actions


def rows_from_replay(path: str | Path) -> list[dict]:
    rows = []
    for file in sorted(Path(path).glob("*.jsonl")) if Path(path).is_dir() else [Path(path)]:
        with file.open() as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("type") == "transition" or "observation" in row:
                    if row.get("observation", {}).get("schema") == "crawl-general-v1":
                        rows.append(row)
    return rows


def _actions(state):
    actions = state.get("actions", [])
    if isinstance(actions, dict):
        return [actions[key] for key in sorted(actions, key=lambda x: int(x))]
    return list(actions)


def train_behavioral_clone(rows: list[dict], epochs: int = 3,
                           seed: int = 0) -> tuple[ActionValueModel, dict]:
    if not rows:
        raise ValueError("replay contains no usable transitions")
    random.seed(seed)
    torch.manual_seed(seed)
    model = ActionValueModel()
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    losses = []
    usable = 0
    for _ in range(epochs):
        order = list(range(len(rows)))
        random.shuffle(order)
        total = 0.0
        for row_index in order:
            state = rows[row_index]["observation"]
            actions = _actions(state)
            chosen = rows[row_index].get("action")
            target = rows[row_index].get("action_index")
            if target is None:
                target = next((i for i, action in enumerate(actions) if action == chosen), -1)
            if not 0 <= int(target) < len(actions):
                continue
            scores = model(tensor_for_actions(state, actions)).unsqueeze(0)
            loss = nn.functional.cross_entropy(scores, torch.tensor([int(target)]))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += float(loss.detach())
            usable += 1
        losses.append(total / max(1, usable))
    return model, {"rows": len(rows), "usable": usable,
                   "epochs": epochs, "losses": losses, "objective": "behavioral_cloning"}


def train_q_finetune(model: ActionValueModel, rows: list[dict], epochs: int = 1,
                     gamma: float = 0.99) -> dict:
    """One conservative score-to-go update; terminal score is the target."""
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-4, weight_decay=1e-5)
    usable = 0
    losses = []
    for _ in range(epochs):
        total = 0.0
        for row in rows:
            state = row.get("observation")
            actions = _actions(state or {})
            if not actions:
                continue
            chosen = row.get("action")
            index = row.get("action_index")
            if index is None:
                index = next((i for i, a in enumerate(actions) if a == chosen), -1)
            if not 0 <= int(index) < len(actions):
                continue
            target = float(row.get("return", row.get("reward", 0.0)))
            prediction = model(tensor_for_actions(state, actions))[int(index)]
            loss = (prediction - target) ** 2
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            total += float(loss.detach()); usable += 1
        losses.append(total / max(1, usable))
    return {"usable": usable, "epochs": epochs, "losses": losses,
            "objective": "score_to_go_finetune", "gamma": gamma}


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
