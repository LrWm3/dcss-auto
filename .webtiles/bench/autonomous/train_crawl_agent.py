#!/usr/bin/env python3
"""Restartable unattended Crawl policy-training orchestrator, V1."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
import time
import torch
import storage
from pathlib import Path

from collect import run_episode
from counterfactual import evaluate_checkpoint
from evaluate import comparison, evaluate_model
from selection import (ensure_protocol, screen_decision, prepare_batch, run_batch,
                       promote_confirmed, audit_due, latest_champion, run_lock)
from general_env import BASE_RC, ENGINE, sha
from model import load_model, save_model
from train_model import rows_from_replay, train_behavioral_clone, train_q_finetune, train_counterfactual_preferences

DEFAULT_SEEDS = ["1760771545328102746", "1760771545328102747",
                 "1760771545328102748", "1760771545328102749",
                 "1760771545328102750"]


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def append(path: Path, value: dict) -> None:
    storage.guard()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


def jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    with storage.open_text(path) as stream:
        return sum(1 for line in stream if line.strip())


def artifact_counts(run_dir: Path) -> dict:
    """Return cheap health counters for latest_status.json.

    These counters are deliberately derived from durable JSONL artifacts so a
    restarted orchestrator can report the same totals without another state
    database.
    """
    replay_files = storage.replay_files(run_dir / "replay")
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
    failures = interrupted = 0
    for path in (run_dir / "failures").glob("**/*.jsonl"):
        with path.open() as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                failures += int("error" in record)
                interrupted += int(record.get("type") == "transition")
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
        "interrupted_replay_rows": interrupted,
    }


def prepare(run_dir: Path, args) -> dict:
    for name in ("champions", "candidates", "replay", "state_archive",
                 "evaluations", "rollouts", "metrics", "actors",
                 "failures/crashes", "failures/invalid_states", "failures/timeouts"):
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    config_path = run_dir / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        config["storage"] = storage.limits()
        config["decisions_per_floor"] = config.get("decisions_per_floor", config.get("steps_per_episode", 2000))
        config["total_decisions"] = config.get("total_decisions", args.total_steps)
        config["budget_version"] = "cumulative_per_floor_v1"
        write(config_path, config)
        return config
    config = {
        "schema_version": 1, "environment_version": "crawl-general-v1",
        "action_version": "crawl-semantic-actions-v1",
        "feature_version": __import__("features").FEATURE_VERSION,
        "bootstrap_episodes": args.bootstrap_episodes,
        "bootstrap_epochs": args.bootstrap_epochs,
        "actor_episodes": args.actor_episodes,
        "evaluation_episodes": args.evaluation_episodes,
        "decisions_per_floor": args.steps,
        "total_decisions": args.total_steps,
        "budget_version": "cumulative_per_floor_v1",
        "counterfactual_top_k": args.top_k,
        "counterfactual_random_k": args.random_k,
        "counterfactual_continuations": args.continuations,
        "counterfactual_steps": args.counterfactual_steps,
        "epsilon": args.epsilon, "promotion_margin": args.promotion_margin,
        "seeds": DEFAULT_SEEDS, "started_unix": time.time(),
        "storage": storage.limits(),
    }
    write(config_path, config)
    write(run_dir / "environment_version.txt", {
        "engine": str(ENGINE), "engine_sha256": sha(ENGINE),
        "bridge": "general_bridge.lua", "source_rc": str(BASE_RC),
    })
    return config


def status(run_dir: Path, phase: str, **extra) -> None:
    storage.guard()
    previous = {}
    if (run_dir / "latest_status.json").exists():
        previous = json.loads((run_dir / "latest_status.json").read_text())
    value = {"run_dir": str(run_dir), "phase": phase,
             "updated_unix": time.time(), "counts": artifact_counts(run_dir),
             "completed_cycles": previous.get("completed_cycles", 0),
             "storage": storage.health(run_dir),
             **extra}
    write(run_dir / "latest_status.json", value)
    append(run_dir / "metrics" / "training.jsonl", value)


def collect_parallel(run_dir: Path, seeds: list[str], label: str, episodes: int,
                     steps: int, model: Path | None, epsilon: float,
                     archive: bool, total_steps: int = 100000) -> list[dict]:
    selected = [seeds[i % len(seeds)] for i in range(episodes)]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(4,len(selected)))) as pool:
        # A restarted partial cycle must not append a second episode to the
        # previous trajectory. Preserve unfinished files for debugging.
        for i in range(len(selected)):
            path = run_dir / "replay" / f"{label}-{i}.jsonl"
            if path.exists() and not storage.result_path(path).exists():
                destination = run_dir / "failures" / "invalid_states" / f"{label}-{i}-{time.time_ns()}.jsonl"
                path.replace(destination)
        pending = [(i, seed) for i, seed in enumerate(selected)
                   if not (run_dir / "replay" / f"{label}-{i}.result.json").exists()]
        for i in range(len(selected)):
            result_path = run_dir / "replay" / f"{label}-{i}.result.json"
            if result_path.exists():
                results.append(json.loads(result_path.read_text()))
        jobs = [(i, pool.submit(
            run_episode, run_dir / "actors" / f"{label}-{i}", seed, steps,
            run_dir / "replay" / f"{label}-{i}.jsonl", model, epsilon,
            run_dir / "state_archive" if archive else None, label, archive, total_steps))
            for i, seed in pending]
        for i, job in jobs:
            try:
                result = job.result()
            except Exception as exc:
                result = {"error": str(exc), "label": label, "actor": i}
                append(run_dir / "failures" / "crashes" / "actors.jsonl", result)
            results.append(result)
            append(run_dir / "metrics" / "progression.jsonl", result)
    storage.maintain(run_dir)
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
    parser.add_argument("--steps", "--decisions-per-floor", type=int, default=2000,
                        help="cumulative decision allowance per distinct floor")
    parser.add_argument("--total-steps", type=int, default=100000, help="whole-game emergency decision cap")
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
        current["storage"] = storage.health(run_dir)
        if current["storage"]["paused"]:
            current["phase"] = "paused_low_disk"
        if current.get("confirmation_status") and Path(current["confirmation_status"]).exists():
            current["confirmation_progress"] = json.loads(Path(current["confirmation_status"]).read_text())
        print(json.dumps(current,indent=2,sort_keys=True))
        return
    with run_lock(run_dir):
        run_training(args, run_dir)


def run_training(args, run_dir):
    run_dir.mkdir(parents=True, exist_ok=True)
    storage.configure(run_dir)
    storage.guard()
    config = prepare(run_dir, args)
    ensure_protocol(run_dir)
    storage.maintain(run_dir)
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
                         config["decisions_per_floor"], None, 0.0, True, config["total_decisions"])
        rows = rows_from_replay(run_dir / "replay")
        if not rows:
            raise RuntimeError("bootstrap generated no replay rows")
        model, metadata = train_behavioral_clone(rows, epochs=config.get("bootstrap_epochs",10), seed=0)
        champion = run_dir / "champions" / "V0.pt"
        save_model(champion, model, {**metadata, "policy_version": "V0", "bootstrap": True})
        version = "V0"
        status(run_dir, "bootstrapped", champion=str(champion), replay_rows=len(rows))

    cycle = start_cycle
    audit_due(run_dir, config, start_cycle)
    end_cycle = None if args.forever else start_cycle + args.cycles
    while end_cycle is None or cycle < end_cycle:
        label = f"cycle-{cycle:04d}"
        # Resume a frozen confirmation before any retraining can overwrite its
        # candidate or repeat counterfactual collection for this partial cycle.
        pending = run_dir / "evaluations" / "confirmations" / label
        if (pending / "manifest.json").exists():
            status(run_dir, "confirming", cycle=cycle,
                   confirmation_status=str(pending / "status.json"))
            decision = run_batch(pending)
            promoted = promote_confirmed(run_dir, pending)
            champion = latest_champion(run_dir)
            version = champion.stem
            cycle += 1
            status(run_dir, "cycle_complete", cycle=cycle-1,
                   completed_cycles=cycle, champion=str(champion),
                   promoted=bool(promoted), promotion_decision=decision)
            audit_due(run_dir, config, cycle)
            continue
        status(run_dir, "actor_collecting", cycle=cycle, champion=str(champion))
        actors = collect_parallel(run_dir, seeds, label, config["actor_episodes"],
                                  config["decisions_per_floor"], champion,
                                  config["epsilon"], True, config["total_decisions"])
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
                    append(run_dir / "replay" / f"{label}-counterfactual.jsonl", {
                        "type": "transition", "observation": row["observation"],
                        "action": row["action"], "action_index": row["action_index"],
                        "return": row["empirical_return"],
                        "policy_version": label + ":counterfactual",
                    })
                if cf_records:
                    write(run_dir / "replay" / f"{label}-counterfactual.result.json",
                          {"steps": len(cf_records)})
                    storage.maintain(run_dir)
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
                preference_meta = train_counterfactual_preferences(updated_model, cf_rows, anchors=rows)
                save_model(candidate, updated_model,
                           {**payload.get("metadata", {}), "counterfactual": q_meta,
                            "counterfactual_policy_update": preference_meta})
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
            config["decisions_per_floor"], 0.0, version, config["total_decisions"]))
        candidate_eval = comparison(evaluate_model(
            candidate, run_dir / "evaluations" / f"{label}-candidate", eval_seeds,
            config["decisions_per_floor"], 0.0, label, config["total_decisions"]))
        evaluation = {"cycle": cycle, "champion": champion_eval,
                      "candidate": candidate_eval, "candidate_path": str(candidate),
                      "model_hashes": {"champion":sha(champion), "candidate":sha(candidate)},
                      "role": "screen", "protocol":"screen-confirm-audit-v1",
                      "train": train_meta, "counterfactual_rows": len(cf_records)}
        append(run_dir / "evaluations" / "paired_seeds.jsonl", evaluation)
        screening = screen_decision(champion_eval, candidate_eval)
        decision, promote = screening, False
        write(run_dir / "evaluations" / "screens" / f"{label}.json", {"evaluation":evaluation,"decision":screening})
        if screening["state"] == "awaiting_confirmation":
            folder = prepare_batch(run_dir, label, champion, candidate, config)
            status(run_dir, "confirming", cycle=cycle, champion=str(champion),
                   candidate=str(candidate), confirmation_status=str(folder / "status.json"),
                   screen_decision=screening)
            decision = run_batch(folder)
            promoted = promote_confirmed(run_dir, folder)
            promote = bool(promoted)
            if promote:
                champion = latest_champion(run_dir)
                version = champion.stem
        status(run_dir, "cycle_complete", cycle=cycle, champion=str(champion),
               completed_cycles=cycle + 1,
               candidate=str(candidate), promoted=promote, evaluation=evaluation,
               promotion_decision=decision)
        cycle += 1
        if cycle % ensure_protocol(run_dir)["audit_every_completed_cycles"] == 0:
            status(run_dir, "auditing", cycle=cycle, champion=str(champion))
            audit_due(run_dir, config, cycle)
    status(run_dir, "idle", champion=str(champion),
           completed_cycles=cycle)


if __name__ == "__main__":
    main()
