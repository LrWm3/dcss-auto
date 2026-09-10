#!/usr/bin/env python3
"""Restartable unattended Crawl policy-training orchestrator, V1."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
import time
import torch
from pathlib import Path

from collect import run_episode
from counterfactual import evaluate_checkpoint
from evaluate import comparison, evaluate_model, promotion_decision
from general_env import BASE_RC, ENGINE, sha
from model import load_model, save_model
from train_model import rows_from_replay, train_behavioral_clone, train_q_finetune

DEFAULT_SEEDS = ["1760771545328102746", "1760771545328102747",
                 "1760771545328102748", "1760771545328102749",
                 "1760771545328102750"]


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def append(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


def jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.open() if line.strip())


def artifact_counts(run_dir: Path) -> dict:
    """Return cheap health counters for latest_status.json.

    These counters are deliberately derived from durable JSONL artifacts so a
    restarted orchestrator can report the same totals without another state
    database.
    """
    replay_files = sorted((run_dir / "replay").glob("*.jsonl"))
    replay_rows = sum(jsonl_count(path) for path in replay_files)
    progression = run_dir / "metrics" / "progression.jsonl"
    games = actions = 0
    if progression.exists():
        for line in progression.open():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            games += 1
            actions += int(row.get("steps", 0) or 0)
    failures = sum(
        jsonl_count(path)
        for path in (run_dir / "failures").glob("**/*.jsonl")
    )
    return {
        "games_generated": games,
        "actions_generated": actions,
        "replay_rows": replay_rows,
        "state_archive_cases": len(list((run_dir / "state_archive").glob("*/case.json"))),
        "counterfactual_rows": jsonl_count(
            run_dir / "rollouts" / "counterfactual_results.jsonl"),
        "evaluation_rows": jsonl_count(
            run_dir / "evaluations" / "paired_seeds.jsonl"),
        "failure_rows": failures,
    }


def prepare(run_dir: Path, args) -> dict:
    for name in ("champions", "candidates", "replay", "state_archive",
                 "evaluations", "rollouts", "metrics", "actors",
                 "failures/crashes", "failures/invalid_states", "failures/timeouts"):
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    config_path = run_dir / "config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    config = {
        "schema_version": 1, "environment_version": "crawl-general-v1",
        "action_version": "crawl-semantic-actions-v1",
        "feature_version": __import__("features").FEATURE_VERSION,
        "bootstrap_episodes": args.bootstrap_episodes,
        "bootstrap_epochs": args.bootstrap_epochs,
        "actor_episodes": args.actor_episodes,
        "evaluation_episodes": args.evaluation_episodes,
        "steps_per_episode": args.steps,
        "counterfactual_top_k": args.top_k,
        "counterfactual_random_k": args.random_k,
        "counterfactual_continuations": args.continuations,
        "counterfactual_steps": args.counterfactual_steps,
        "epsilon": args.epsilon, "promotion_margin": args.promotion_margin,
        "seeds": DEFAULT_SEEDS, "started_unix": time.time(),
    }
    write(config_path, config)
    write(run_dir / "environment_version.txt", {
        "engine": str(ENGINE), "engine_sha256": sha(ENGINE),
        "bridge": "general_bridge.lua", "source_rc": str(BASE_RC),
    })
    return config


def status(run_dir: Path, phase: str, **extra) -> None:
    previous = {}
    if (run_dir / "latest_status.json").exists():
        previous = json.loads((run_dir / "latest_status.json").read_text())
    value = {"run_dir": str(run_dir), "phase": phase,
             "updated_unix": time.time(), "counts": artifact_counts(run_dir),
             "completed_cycles": previous.get("completed_cycles", 0),
             **extra}
    write(run_dir / "latest_status.json", value)
    append(run_dir / "metrics" / "training.jsonl", value)


def collect_parallel(run_dir: Path, seeds: list[str], label: str, episodes: int,
                     steps: int, model: Path | None, epsilon: float,
                     archive: bool) -> list[dict]:
    selected = [seeds[i % len(seeds)] for i in range(episodes)]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(4,len(selected)))) as pool:
        jobs = [pool.submit(
            run_episode, run_dir / "actors" / f"{label}-{i}", seed, steps,
            run_dir / "replay" / f"{label}-{i}.jsonl", model, epsilon,
            run_dir / "state_archive" if archive else None, label, archive)
            for i, seed in enumerate(selected)]
        for i, job in enumerate(jobs):
            try:
                result = job.result()
            except Exception as exc:
                result = {"error": str(exc), "label": label, "actor": i}
                append(run_dir / "failures" / "crashes" / "actors.jsonl", result)
            results.append(result)
            append(run_dir / "metrics" / "progression.jsonl", result)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--status", action="store_true", help="print current status and live artifact counts")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--forever", action="store_true",
                        help="continue cycles until the process is stopped")
    parser.add_argument("--bootstrap-episodes", type=int, default=5)
    parser.add_argument("--bootstrap-epochs", type=int, default=10)
    parser.add_argument("--actor-episodes", type=int, default=2)
    parser.add_argument("--evaluation-episodes", type=int, default=5)
    parser.add_argument("--steps", type=int, default=2000)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--random-k", type=int, default=2)
    parser.add_argument("--continuations", type=int, default=2)
    parser.add_argument("--counterfactual-steps", type=int, default=8)
    parser.add_argument("--epsilon", type=float, default=0.1)
    parser.add_argument("--promotion-margin", type=float, default=0.0)
    args = parser.parse_args()
    torch.set_num_threads(1)
    run_dir = args.run_dir.resolve()
    if args.status:
        current = json.loads((run_dir / "latest_status.json").read_text())
        current["counts"] = artifact_counts(run_dir)
        print(json.dumps(current,indent=2,sort_keys=True))
        return
    config = prepare(run_dir, args)
    seeds = list(config.get("seeds", DEFAULT_SEEDS))
    previous_status = {}
    if (run_dir / "latest_status.json").exists():
        try:
            previous_status = json.loads((run_dir / "latest_status.json").read_text())
        except json.JSONDecodeError:
            previous_status = {}
    start_cycle = int(previous_status.get("completed_cycles", 0))
    status(run_dir, "starting", resume_from_cycle=start_cycle)

    champion_paths = sorted((run_dir / "champions").glob("V*.pt"),
                            key=lambda p: int(p.stem[1:]))
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
        model, metadata = train_behavioral_clone(rows, epochs=config.get("bootstrap_epochs",10), seed=0)
        champion = run_dir / "champions" / "V0.pt"
        save_model(champion, model, {**metadata, "policy_version": "V0", "bootstrap": True})
        version = "V0"
        status(run_dir, "bootstrapped", champion=str(champion), replay_rows=len(rows))

    cycle = start_cycle
    end_cycle = None if args.forever else start_cycle + args.cycles
    while end_cycle is None or cycle < end_cycle:
        label = f"cycle-{cycle:04d}"
        status(run_dir, "actor_collecting", cycle=cycle, champion=str(champion))
        actors = collect_parallel(run_dir, seeds, label, config["actor_episodes"],
                                  config["steps_per_episode"], champion,
                                  config["epsilon"], True)
        rows = rows_from_replay(run_dir / "replay")
        candidate_model, _ = load_model(champion)
        candidate_model, train_meta = train_behavioral_clone(
            rows, epochs=2, seed=len(rows), model=candidate_model)
        train_meta["ordinary_play_returns"] = train_q_finetune(candidate_model, rows)
        candidate = run_dir / "candidates" / f"{label}.pt"
        save_model(candidate, candidate_model, {**train_meta, "candidate": label})
        status(run_dir, "counterfactual_collecting", cycle=cycle,
               candidate=str(candidate), actors=len(actors))

        cf_records = []
        archive_cases = sorted((run_dir / "state_archive").glob("*/case.json"))
        if archive_cases:
            case = archive_cases[cycle % len(archive_cases)].parent
            try:
                cf_records = evaluate_checkpoint(
                    case, run_dir / "counterfactual", candidate,
                    config["counterfactual_top_k"], config["counterfactual_random_k"],
                    config["counterfactual_continuations"], config["counterfactual_steps"])
                for row in cf_records:
                    append(run_dir / "rollouts" / "counterfactual_results.jsonl", row)
                    append(run_dir / "replay" / "counterfactual.jsonl", {
                        "type": "transition", "observation": row["observation"],
                        "action": row["action"], "action_index": row["action_index"],
                        "return": row["empirical_return"],
                        "policy_version": label + ":counterfactual",
                    })
                # The branch result is now used immediately as an empirical
                # score-to-go target, rather than waiting for the next cycle.
                # This is intentionally a small conservative update; the
                # archive/replay record remains the durable source of truth.
                updated_model, payload = load_model(candidate)
                cf_rows = [{"observation": row["observation"],
                            "action": row["action"],
                            "action_index": row["action_index"],
                            "return": row["empirical_return"]}
                           for row in cf_records]
                q_meta = train_q_finetune(updated_model, cf_rows, epochs=1)
                save_model(candidate, updated_model,
                           {**payload.get("metadata", {}), "counterfactual": q_meta})
            except Exception as exc:
                append(run_dir / "failures" / "invalid_states" / "counterfactual.jsonl",
                       {"error": str(exc), "case": str(case)})

        status(run_dir, "evaluating", cycle=cycle, candidate=str(candidate),
               counterfactual_rows=len(cf_records))
        eval_seeds = [str(910000000000 + i) for i in range(config["evaluation_episodes"])]
        if set(eval_seeds) & set(seeds):
            raise ValueError("evaluation seeds overlap training seeds")
        champion_eval = comparison(evaluate_model(
            champion, run_dir / "evaluations" / f"{label}-champion", eval_seeds,
            config["steps_per_episode"], 0.0, version))
        candidate_eval = comparison(evaluate_model(
            candidate, run_dir / "evaluations" / f"{label}-candidate", eval_seeds,
            config["steps_per_episode"], 0.0, label))
        evaluation = {"cycle": cycle, "champion": champion_eval,
                      "candidate": candidate_eval, "candidate_path": str(candidate),
                      "train": train_meta, "counterfactual_rows": len(cf_records)}
        append(run_dir / "evaluations" / "paired_seeds.jsonl", evaluation)
        decision = promotion_decision(champion_eval, candidate_eval,
                                      float(config["promotion_margin"]))
        promote = decision["promote"]
        if promote:
            promoted = run_dir / "champions" / f"V{cycle + 1}.pt"
            shutil.copy2(candidate, promoted)
            champion, version = promoted, promoted.stem
        status(run_dir, "cycle_complete", cycle=cycle, champion=str(champion),
               completed_cycles=cycle + 1,
               candidate=str(candidate), promoted=promote, evaluation=evaluation,
               promotion_decision=decision)
        cycle += 1
    status(run_dir, "idle", champion=str(champion),
           completed_cycles=cycle)


if __name__ == "__main__":
    main()
