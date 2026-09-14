#!/usr/bin/env python3
"""Unattended Crawl policy-training orchestrator, V1.

The run is restartable.  It creates teacher data, trains a variable-action
behavioral-cloning policy, runs parallel actors, evaluates a challenger,
spends simulator compute on counterfactual branches, and promotes only a
challenger that improves the held-out metric.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
import sys
import time
from pathlib import Path

from collect import run_episode
from counterfactual import evaluate_checkpoint
from evaluate import comparison, evaluate_model
from model import save_model
from train_model import rows_from_replay, train_behavioral_clone, train_q_finetune


DEFAULT_SEEDS = ["1760771545328102746", "1760771545328102747",
                 "1760771545328102748", "1760771545328102749",
                 "1760771545328102750"]


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _append(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


def prepare(run_dir: Path, args) -> dict:
    for name in ("champions", "candidates", "replay", "state_archive",
                 "evaluations", "rollouts", "metrics", "failures/crashes",
                 "failures/invalid_states", "failures/timeouts"):
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    config_path = run_dir / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {
            "schema_version": 1, "environment_version": "crawl-general-v1",
            "action_version": "crawl-semantic-actions-v1",
            "bootstrap_episodes": args.bootstrap_episodes,
            "actor_episodes": args.actor_episodes,
            "evaluation_episodes": args.evaluation_episodes,
            "steps_per_episode": args.steps,
            "counterfactual_top_k": args.top_k,
            "counterfactual_random_k": args.random_k,
            "counterfactual_continuations": args.continuations,
            "counterfactual_steps": args.counterfactual_steps,
            "epsilon": args.epsilon, "promotion_margin": args.promotion_margin,
            "seeds": DEFAULT_SEEDS,
            "started_unix": time.time(),
        }
        _write(config_path, config)
    if not (run_dir / "environment_version.txt").exists():
        _write(run_dir / "environment_version.txt", {
            "engine": str(__import__("general_env").ENGINE),
            "engine_sha256": __import__("general_env").sha(__import__("general_env").ENGINE),
            "bridge": "general_bridge.lua",
            "source_rc": str(__import__("general_env").BASE_RC),
        })
    return config


def status(run_dir: Path, phase: str, **extra) -> dict:
    current = {"run_dir": str(run_dir), "phase": phase, "updated_unix": time.time(), **extra}
    _write(run_dir / "latest_status.json", current)
    _append(run_dir / "metrics" / "training.jsonl", current)
    return current


def collect_parallel(run_dir: Path, seeds: list[str], label: str, episodes: int,
                     steps: int, model: Path | None, epsilon: float,
                     archive: bool = False) -> list[dict]:
    selected = [seeds[i % len(seeds)] for i in range(episodes)]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(selected))) as pool:
        jobs = []
        for index, seed in enumerate(selected):
            jobs.append(pool.submit(
                run_episode, run_dir / "actors" / f"{label}-{index}", seed, steps,
                run_dir / "replay" / f"{label}-{index}.jsonl", model, epsilon,
                run_dir / "state_archive" if archive else None, label, archive))
        for index, job in enumerate(jobs):
            try:
                result = job.result()
            except Exception as exc:
                result = {"error": str(exc), "label": label, "actor": index}
                _append(run_dir / "failures" / "crashes" / "actors.jsonl", result)
            results.append(result)
            _append(run_dir / "metrics" / "progression.jsonl", result)
    return results


def train_candidate(run_dir: Path, label: str) -> tuple[Path, dict]:
    rows = rows_from_replay(run_dir / "replay")
    model, metadata = train_behavioral_clone(rows, epochs=2, seed=len(rows))
    output = run_dir / "candidates" / f"{label}.pt"
    save_model(output, model, {**metadata, "candidate": label})
    return output, metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--bootstrap-episodes", type=int, default=2)
    parser.add_argument("--actor-episodes", type=int, default=2)
    parser.add_argument("--evaluation-episodes", type=int, default=2)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--random-k", type=int, default=2)
    parser.add_argument("--continuations", type=int, default=2)
    parser.add_argument("--counterfactual-steps", type=int, default=8)
    parser.add_argument("--epsilon", type=float, default=0.1)
    parser.add_argument("--promotion-margin", type=float, default=0.0)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    config = prepare(run_dir, args)
    seeds = list(config.get("seeds", DEFAULT_SEEDS))
    status(run_dir, "starting", champion=None)

    champion_paths = sorted((run_dir / "champions").glob("*.pt"))
    if champion_paths:
        champion = champion_paths[-1]
        version = champion.stem
    else:
        status(run_dir, "bootstrap_collecting")
        collect_parallel(run_dir, seeds, "bootstrap", config["bootstrap_episodes"],
                         config["steps_per_episode"], None, 0.0, True)
        rows = rows_from_replay(run_dir / "replay")
        if not rows:
            raise RuntimeError("bootstrap generated no replay rows")
        model, metadata = train_behavioral_clone(rows, epochs=3, seed=0)
        champion = run_dir / "champions" / "V0.pt"
        save_model(champion, model, {**metadata, "policy_version": "V0", "bootstrap": True})
        version = "V0"
        status(run_dir, "bootstrapped", champion=str(champion), replay_rows=len(rows))

    for cycle in range(args.cycles):
        label = f"cycle-{cycle:04d}"
        status(run_dir, "actor_collecting", cycle=cycle, champion=str(champion))
        actor_results = collect_parallel(
            run_dir, seeds, label, config["actor_episodes"], config["steps_per_episode"],
            champion, config["epsilon"], False)
        candidate, train_meta = train_candidate(run_dir, label)
        status(run_dir, "counterfactual_collecting", cycle=cycle,
               candidate=str(candidate), actors=len(actor_results))

        archive_cases = sorted((run_dir / "state_archive").glob("*/case.json"))
        cf_records = []
        if archive_cases:
            case = archive_cases[0].parent
            try:
                cf_records = evaluate_checkpoint(
                    case, run_dir / "counterfactual", candidate,
                    config["counterfactual_top_k"], config["counterfactual_random_k"],
                    config["counterfactual_continuations"], config["counterfactual_steps"])
                for row in cf_records:
                    _append(run_dir / "rollouts" / "counterfactual_results.jsonl", row)
                    # Counterfactual labels are kept as separate replay rows;
                    # the next cycle can use them for score-to-go updates.
                    _append(run_dir / "replay" / "counterfactual.jsonl", {
                        "type": "transition", "observation": row["observation"],
                        "action": row["action"], "action_index": row["action_index"],
                        "return": row["empirical_return"],
                        "policy_version": label + ":counterfactual",
                    })
            except Exception as exc:
                _append(run_dir / "failures" / "invalid_states" / "counterfactual.jsonl",
                        {"error": str(exc), "case": str(case)})

        status(run_dir, "evaluating", cycle=cycle, candidate=str(candidate),
               counterfactual_rows=len(cf_records))
        eval_seeds = seeds[:config["evaluation_episodes"]]
        champion_eval = comparison(evaluate_model(
            champion, run_dir / "evaluations" / f"{label}-champion", eval_seeds,
            config["steps_per_episode"], 0.0, version))
        candidate_eval = comparison(evaluate_model(
            candidate, run_dir / "evaluations" / f"{label}-candidate", eval_seeds,
            config["steps_per_episode"], 0.0, label))
        evaluation = {"cycle": cycle, "champion": champion_eval,
                      "candidate": candidate_eval, "candidate_path": str(candidate),
                      "train": train_meta, "counterfactual_rows": len(cf_records)}
        _append(run_dir / "evaluations" / "paired_seeds.jsonl", evaluation)
        # Actual terminal scores are primary.  Before deaths/wins occur, the
        # progression metric is explicitly a diagnostic proxy, not a new game
        # reward.  The same metric is used for both policies on paired seeds.
        left = champion_eval["mean_score"] if champion_eval["mean_score"] is not None else champion_eval["mean_progression"]
        right = candidate_eval["mean_score"] if candidate_eval["mean_score"] is not None else candidate_eval["mean_progression"]
        promote = right > left + float(config["promotion_margin"])
        if promote:
            promoted = run_dir / "champions" / f"V{cycle + 1}.pt"
            shutil.copy2(candidate, promoted)
            champion, version = promoted, promoted.stem
        status(run_dir, "cycle_complete", cycle=cycle, champion=str(champion),
               candidate=str(candidate), promoted=promote, evaluation=evaluation)

    status(run_dir, "idle", champion=str(champion), completed_cycles=args.cycles)


if __name__ == "__main__":
    main()
