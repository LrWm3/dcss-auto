"""Evaluate a small legal-action branch set from an exact Crawl checkpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from collect import _progression
from general_env import GeneralEnvironment
from policy import Policy
from model import action_scores, tensor_for_actions
import torch
import storage
from data_split import assert_training_seed
from exploration_score import learning_score, report_fields, VERSION as EXPLORATION_VERSION


def _actions(state):
    actions = state.get("actions", [])
    if isinstance(actions, dict):
        return [actions[key] for key in sorted(actions, key=lambda x: int(x))]
    return list(actions)


def empirical_return(outcomes, continuations):
    versions = {x.get('score_version') for x in outcomes if not x.get('error')}
    if len(versions) > 1:
        return None
    numeric = [float(learning_score(x)) for x in outcomes
               if x.get('score_status') in ('final_official', 'cutoff_official')
               and learning_score(x) is not None and not x.get('error')]
    return sum(numeric) / continuations if continuations > 0 and len(numeric) == continuations else None


def evaluate_checkpoint(case: str | Path, workspace: str | Path,
                        model_path: str | Path, top_k: int = 3,
                        random_k: int = 2, continuations: int = 2,
                        continuation_steps: int = 8, max_workers: int = 6,
                        include_teacher: bool = False) -> list[dict]:
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
    # Different archived states should not repeatedly receive the same random
    # alternatives; keep the choice reproducible for exact replay.
    case_seed = int.from_bytes(hashlib.blake2b(str(case).encode(), digest_size=8).digest(), 'little')
    rng = random.Random(case_seed)
    remaining = [i for i in range(len(actions)) if i not in ranked]
    rng.shuffle(remaining)
    candidates = ranked + remaining[:random_k]
    if include_teacher:
        from teacher import choose_action
        suggestion = choose_action(state)
        if suggestion not in candidates:
            candidates.append(suggestion)
    def rollout(task):
        action_index, continuation = task
        env = GeneralEnvironment(Path(workspace) / f"branch-{action_index}-{continuation}")
        env.record_events = False
        completed = False
        try:
            current = env.launch(case)
            if _actions(current) != actions:
                raise ValueError('restored legal actions differ from probe; refusing index mismatch')
            current = env.step(action_index)
            policy = Policy(model_policy.model, epsilon=0.15,
                            rng=random.Random(continuation))
            for _ in range(continuation_steps - 1):
                if current.get("terminal"):
                    break
                current = env.step(policy.choose(current)[0])
            outcome = {
                "progression": _progression(current),
                "score": current.get("score"),
                **report_fields(current),
                "terminal": current.get("terminal"),
                "level": current.get("level"), "turn": current.get("turn"),
                "score_status": 'final_official' if current.get('terminal') else
                    ('cutoff_official' if current.get('score_status') == 'live_official' else 'unavailable'),
            }
            completed = True
            return outcome
        except Exception as exc:
            return {"error": str(exc)}
        finally:
            env.close()
            if completed:
                storage.finish_logs(env.works)

    tasks = [(action_index, continuation) for action_index in candidates
             for continuation in range(continuations)]
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(tasks)))) as pool:
        # map retains task order, independently of worker completion order.
        results = dict(zip(tasks, pool.map(rollout, tasks)))
    records = []
    for action_index in candidates:
        outcomes = [results[action_index, c] for c in range(continuations)]
        records.append({
            "type": "counterfactual", "case": str(case),
            "observation": state, "action": actions[action_index],
            "action_index": action_index, "model_value": float(scores[action_index]),
            "policy_logit": float(scores[action_index]),
            "predicted_log_score": float(predicted_values[action_index]),
            "outcomes": outcomes, "empirical_return": empirical_return(outcomes, continuations),
            "continuations": continuations,
            "return_protocol": ("exploration_score_at_terminal_or_fixed_horizon_v1"
                if state.get('score_version') == EXPLORATION_VERSION else
                "official_score_at_terminal_or_fixed_horizon_v2"),
            "score_version": state.get('score_version'),
            "continuation_steps": continuation_steps,
            "continuation_exploration": "epsilon_0.15_uniform_legal_actions",
            "randomness": "identical engine RNG restored; paired policy sampling seeds across first actions",
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
    torch.set_num_threads(1)
    rows = evaluate_checkpoint(args.case, args.workspace, args.model,
                               args.top_k, args.random_k, args.continuations, args.steps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    print(json.dumps({"rows": len(rows), "output": str(args.output)}))


if __name__ == "__main__":
    main()
