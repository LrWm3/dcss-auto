"""Reproducible retraining diagnostics and an independent cycle-3 audit.

The audit is held out, fixed before launch, and cannot promote a checkpoint.
Offline diagnostics use training replay only, never audit trajectories.
"""
import argparse
import copy
import json
import random
import statistics
from collections import Counter
from pathlib import Path

import torch

import storage
from model import load_model, save_model, tensor_for_actions
from selection import prepare_batch, run_batch, run_lock, write
from train_model import (rows_from_replay, train_behavioral_clone,
                         train_q_finetune, train_counterfactual_preferences)
from score_result import has_episode_score
from evaluate import evaluate_model, comparison


def summarize(source, output):
    screens = []
    for path in sorted((source / "evaluations/screens").glob("*.json")):
        record = json.loads(path.read_text())["evaluation"]
        left, right = record["champion"]["results"], record["candidate"]["results"]
        if not all(has_episode_score(r) for r in left + right):
            continue
        a = {r["seed"]: r["score"] for r in left}
        b = {r["seed"]: r["score"] for r in right}
        assert a.keys() == b.keys()
        screens.append({"cycle": path.stem, "champion_mean": statistics.mean(a.values()),
                        "candidate_mean": statistics.mean(b.values()),
                        "champion_median": statistics.median(a.values()),
                        "candidate_median": statistics.median(b.values()),
                        "candidate_pair_wins": sum(b[s] > a[s] for s in a),
                        "champion_scores": a, "candidate_scores": b})
    cf = [json.loads(line) for line in (source / "rollouts/counterfactual_results.jsonl").open()]
    states = {r["case"]: r["observation"] for r in cf}
    report = {"screens": screens, "counterfactual_coverage": {
        "states": len(states), "actions": len(cf),
        "complete_action_returns": sum(r.get("empirical_return") is not None for r in cf),
        "levels": dict(Counter(s.get("level") for s in states.values())),
        "visible_enemy_counts": dict(Counter(len(s.get("monsters") or []) for s in states.values())),
        "action_kinds": dict(Counter(r["action"]["kind"] for r in cf)),
    }}
    report["ablation_screen"] = {}
    for path in sorted((output / "ablation-screen").glob("*.json")):
        result = json.loads(path.read_text())
        report["ablation_screen"][path.stem] = {
            "mean_score": result["mean_score"],
            "scores": {r["seed"]: r.get("score") for r in result["results"]},
            "errors": result["errors"],
        }
    if (output / "repeat-control.json").exists():
        report["repeat_control"] = [
            {k: r.get(k) for k in ("seed", "score", "steps", "final_level", "model_sha256")}
            for r in json.loads((output / "repeat-control.json").read_text())]
    folder = output / "evaluations/audits/cycle-0003-independent-audit"
    if (folder / "decision.json").exists():
        results = [json.loads(p.read_text()) for p in (folder / "results").glob("*.json")]
        report["audit"] = {"decision": json.loads((folder / "decision.json").read_text())}
        paired = {role: {r["seed"]: r["score"] for r in results
                         if r["policy_version"] == role and has_episode_score(r)}
                  for role in ("champion", "candidate")}
        common = paired["champion"].keys() & paired["candidate"].keys()
        differences = [paired["candidate"][s] - paired["champion"][s] for s in common]
        report["audit"]["paired_outcomes"] = {
            "candidate_wins": sum(d > 0 for d in differences),
            "champion_wins": sum(d < 0 for d in differences),
            "ties": sum(d == 0 for d in differences),
        }
        for role in ("champion", "candidate"):
            rows = [r for r in results if r["policy_version"] == role]
            scores = [r["score"] for r in rows if has_episode_score(r)]
            report["audit"][role] = {
                "games": len(rows), "scored_games": len(scores),
                "mean_score": statistics.mean(scores) if scores else None,
                "median_score": statistics.median(scores) if scores else None,
                "max_score": max(scores, default=None),
                "terminal_count": sum(bool(r.get("terminal")) for r in rows),
                "cutoffs": dict(Counter(r.get("truncation_reason") for r in rows if r.get("truncated"))),
                "final_levels": dict(Counter(r.get("final_level") for r in rows)),
                "errors": sum("error" in r for r in rows),
            }
    write(output / "summary.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "screens"}), flush=True)


def diagnose(source, output):
    rows = rows_from_replay(source / "replay")
    ordinary = [r for r in rows if r.get("teacher_action_index") is not None]
    sample = random.Random(51).sample(ordinary, min(512, len(ordinary)))
    tensors = [tensor_for_actions(r["observation"], r["observation"]["actions"])
               for r in sample]
    baseline, _ = load_model(source / "champions/V0.pt")

    def choices(model):
        with torch.no_grad():
            return [int(model(x).argmax()) for x in tensors]

    original = choices(baseline)

    def measure(model):
        selected = choices(model)
        changes = Counter()
        for row, a, b in zip(sample, original, selected):
            actions = row["observation"]["actions"]
            if a != b:
                changes[actions[a]["kind"] + " -> " + actions[b]["kind"]] += 1
        return {
            "agreement_with_v0": sum(a == b for a, b in zip(original, selected)) / len(sample),
            "teacher_agreement": sum(i == r["teacher_action_index"]
                                     for i, r in zip(selected, sample)) / len(sample),
            "actions": dict(Counter(r["observation"]["actions"][i]["kind"]
                                    for r, i in zip(sample, selected))),
            "changed_actions": dict(changes),
        }

    report = {"rows": len(rows), "teacher_rows": len(ordinary),
              "sample_size": len(sample), "sample_rng": 51,
              "training_episodes": dict(Counter(r.get("episode_seed", "unknown") for r in ordinary)),
              "baseline": measure(baseline), "candidates": {}}
    for path in sorted((source / "candidates").glob("*.pt")):
        model, payload = load_model(path)
        report["candidates"][path.stem] = {**measure(model), "metadata": payload["metadata"]}
    write(output / "diagnostics.json", report)
    print("checkpoint diagnostics saved", flush=True)

    # Reproduce the next scheduled update exactly through its BC stage.
    model, meta = train_behavioral_clone(rows, epochs=2, seed=len(rows), model=copy.deepcopy(baseline))
    report["ablation"] = {"after_bc": {**measure(model), "training": meta}}
    save_model(output / "after_bc.pt", model, meta)
    write(output / "diagnostics.json", report)
    before = {k: v.clone() for k, v in model.net.state_dict().items()}
    critic = train_q_finetune(model, rows)
    unchanged = all(torch.equal(v, model.net.state_dict()[k]) for k, v in before.items())
    assert unchanged, "score critic changed actor parameters"
    report["ablation"]["after_critic"] = {**measure(model), "actor_bitwise_unchanged": unchanged,
                                           "training": critic}
    # Historical usable counterfactual labels, for coverage accounting only.
    cf = [json.loads(line) for line in (source / "rollouts/counterfactual_results.jsonl").open()]
    report["counterfactual_coverage"] = {
        "actions_evaluated": len(cf),
        "actions_with_complete_returns": sum(r.get("empirical_return") is not None for r in cf),
        "states_evaluated": len({r["case"] for r in cf}),
    }
    # The live pipeline uses only the current cycle's one state.
    latest = cf[-3:]
    preferences = [{"observation": r["observation"], "action_index": r["action_index"],
                    "return": r["empirical_return"]} for r in latest]
    update = train_counterfactual_preferences(model, preferences, anchors=rows)
    report["ablation"]["after_latest_preferences"] = {**measure(model), "training": update}
    save_model(output / "reproduced_update.pt", model, report["ablation"])
    write(output / "diagnostics.json", report)
    print("ablation complete", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["audit", "diagnose", "summarize", "ablation-screen", "repeat-control"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(1)
    args.output.mkdir(parents=True, exist_ok=True)
    storage.configure(args.output)
    if args.mode == "diagnose":
        diagnose(args.source, args.output)
    elif args.mode == "summarize":
        summarize(args.source, args.output)
    elif args.mode == "repeat-control":
        from concurrent.futures import ThreadPoolExecutor
        from collect import run_episode
        def trial(index):
            return run_episode(args.output / "repeat-control" / str(index),
                               "16845396515615345340", 2000,
                               model_path=args.source / "champions/V0.pt",
                               epsilon=0, policy_version="V0", snapshot=False,
                               total_steps=100000, data_role="audit")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(trial, range(2)))
        write(args.output / "repeat-control.json", results)
        print(json.dumps([{k: r.get(k) for k in ("score", "steps", "final_level")} for r in results]), flush=True)
    elif args.mode == "ablation-screen":
        for name in ("after_bc", "reproduced_update"):
            path = args.output / "ablation-screen" / (name + ".json")
            if path.exists():
                continue
            results = evaluate_model(args.output / (name + ".pt"),
                                     args.output / "ablation-screen" / name,
                                     [str(910000000000 + i) for i in range(5)],
                                     steps=2000, policy_version=name)
            write(path, comparison(results))
            print(name, comparison(results)["mean_score"], flush=True)
    else:
        with run_lock(args.output):
            config = json.loads((args.source / "config.json").read_text())
            write(args.output / "config.json", config)
            folder = prepare_batch(args.output, "cycle-0003-independent-audit",
                                   args.source / "champions/V0.pt",
                                   args.source / "candidates/cycle-0003.pt", config, "audit")
            print(str(folder / "status.json"), flush=True)
            print(json.dumps(run_batch(folder)), flush=True)


if __name__ == "__main__":
    main()
