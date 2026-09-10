"""Evaluate a small legal-action branch set from an exact Crawl checkpoint."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from collect import _progression
from general_env import GeneralEnvironment
from policy import Policy
from model import action_scores, tensor_for_actions
import torch
import storage
from data_split import assert_training_seed


def _actions(state):
    actions = state.get("actions", [])
    if isinstance(actions, dict):
        return [actions[key] for key in sorted(actions, key=lambda x: int(x))]
    return list(actions)


def evaluate_checkpoint(case: str | Path, workspace: str | Path,
                        model_path: str | Path, top_k: int = 3,
                        random_k: int = 2, continuations: int = 2,
                        continuation_steps: int = 8) -> list[dict]:
    case = Path(case)
    metadata = json.loads((case / "case.json").read_text())
    assert_training_seed(metadata["seed"])
    if metadata.get("data_role", "training") != "training":
        raise ValueError("held-out checkpoints cannot be used for training counterfactuals")
    probe = GeneralEnvironment(Path(workspace) / "probe")
    try:
        state = probe.launch(case)
        actions = _actions(state)
    finally:
        probe.close()
    storage.finish_logs(probe.works)
    model_policy, _ = Policy.from_checkpoint(model_path, epsilon=0.0)
    scores = action_scores(model_policy.model, state, actions)
    with torch.no_grad():
        predicted_values = model_policy.model.value(tensor_for_actions(state, actions))
    ranked = list(reversed(scores.argsort().tolist()))[:top_k]
    rng = random.Random(101)
    remaining = [i for i in range(len(actions)) if i not in ranked]
    rng.shuffle(remaining)
    candidates = ranked + remaining[:random_k]
    records = []
    for action_index in candidates:
        outcomes = []
        for continuation in range(continuations):
            env = GeneralEnvironment(Path(workspace) / f"branch-{action_index}-{continuation}")
            completed = False
            try:
                current = env.launch(case)
                current = env.step(action_index)
                policy = Policy(model_policy.model, epsilon=0.15,
                                rng=random.Random(continuation + action_index * 997))
                for _ in range(continuation_steps - 1):
                    if current.get("terminal"):
                        break
                    current = env.step(policy.choose(current)[0])
                outcomes.append({
                    "progression": _progression(current),
                    "score": current.get("score"),
                    "terminal": current.get("terminal"),
                    "level": current.get("level"), "turn": current.get("turn"),
                })
                completed = True
            except Exception as exc:
                outcomes.append({"error": str(exc)})
            finally:
                env.close()
                if completed:
                    storage.finish_logs(env.works)
        numeric = [float(x["score"]) for x in outcomes
                   if x.get("terminal") and x.get("score") is not None]
        records.append({
            "type": "counterfactual", "case": str(case),
            "observation": state, "action": actions[action_index],
            "action_index": action_index, "model_value": float(scores[action_index]),
            "policy_logit": float(scores[action_index]),
            "predicted_log_score": float(predicted_values[action_index]),
            "outcomes": outcomes, "empirical_return": (
                sum(numeric) / len(numeric) if len(numeric) == continuations else None),
            "continuations": continuations,
        })
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--random-k", type=int, default=2)
    parser.add_argument("--continuations", type=int, default=2)
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = evaluate_checkpoint(args.case, args.workspace, args.model,
                               args.top_k, args.random_k, args.continuations, args.steps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    print(json.dumps({"rows": len(rows), "output": str(args.output)}))


if __name__ == "__main__":
    main()
