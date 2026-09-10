"""Fixed-seed champion/challenger evaluation."""
from __future__ import annotations

import concurrent.futures
import random
from pathlib import Path

from collect import run_episode


def promotion_decision(champion, candidate, margin=0.0):
    left, right = champion["results"], candidate["results"]
    if len(left) != len(right) or len(left) < 5:
        return {"promote": False, "reason": "need at least five complete paired games"}
    differences = []
    for a, b in zip(left, right):
        if (a.get("seed") != b.get("seed") or not all(
                r.get("terminal") and r.get("score") is not None and "error" not in r
                for r in (a, b))):
            return {"promote": False, "reason": "incomplete or invalid score pairs"}
        differences.append(b["score"] - a["score"])
    rng = random.Random(42)
    means = sorted(sum(rng.choices(differences, k=len(differences))) / len(differences)
                   for _ in range(2000))
    lower = means[50]
    return {"promote": lower > margin, "reason": "paired score bootstrap",
            "mean_difference": sum(differences)/len(differences),
            "lower_95_percent": lower, "pairs": len(differences)}


def evaluate_model(model: str | Path, work: str | Path, seeds: list[str],
                   steps: int = 40, epsilon: float = 0.0,
                   policy_version: str = "candidate", total_steps: int = 100000) -> list[dict]:
    work = Path(work)
    jobs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(seeds))) as pool:
        for index, seed in enumerate(seeds):
            jobs.append(pool.submit(
                run_episode, work / f"{policy_version}-{index}", seed, steps,
                None, model, epsilon, None, policy_version, False, total_steps))
        results = []
        for job in jobs:
            try:
                results.append(job.result())
            except Exception as exc:
                results.append({"error": str(exc), "policy_version": policy_version})
    return results


def comparison(results: list[dict]) -> dict:
    valid = [row for row in results if "error" not in row]
    actual = [float(row["score"]) for row in valid
              if row.get("terminal") and row.get("score") is not None]
    progression = [float(row.get("progression", 0)) for row in valid]
    return {
        "episodes": len(valid), "errors": len(results) - len(valid),
        "mean_score": sum(actual) / len(actual) if actual else None,
        "mean_progression": sum(progression) / len(progression) if progression else 0.0,
        "max_progression": max(progression, default=0.0),
        "terminal_count": sum(bool(row.get("terminal")) for row in valid),
        "truncated_count": sum(bool(row.get("truncated")) for row in valid),
        "results": results,
        "metric_used": "actual_score" if len(actual) == len(results) and actual else "incomplete_scores_no_promotion",
    }
