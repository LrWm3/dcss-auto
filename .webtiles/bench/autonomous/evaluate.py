"""Fixed-seed champion/challenger evaluation."""
from __future__ import annotations

import concurrent.futures
from pathlib import Path

from collect import run_episode


def evaluate_model(model: str | Path, work: str | Path, seeds: list[str],
                   steps: int = 40, epsilon: float = 0.0,
                   policy_version: str = "candidate") -> list[dict]:
    work = Path(work)
    jobs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(seeds))) as pool:
        for index, seed in enumerate(seeds):
            jobs.append(pool.submit(
                run_episode, work / f"{policy_version}-{index}", seed, steps,
                None, model, epsilon, None, policy_version, False))
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
        "results": results,
        "metric_used": "actual_score" if actual else "progression_until_terminal_score_exists",
    }
