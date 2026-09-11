"""Fixed-seed champion/challenger evaluation."""
from __future__ import annotations

import concurrent.futures
import random
import hashlib
import json
import tempfile
from pathlib import Path

from collect import run_episode
from score_result import has_episode_score
import storage


def promotion_decision(champion, candidate, margin=0.0):
    """Legacy rule for historical diagnostics only; selection.py governs promotion."""
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
                   policy_version: str = "candidate", total_steps: int = 100000,
                   cache_dir: str | Path | None = None) -> list[dict]:
    work = Path(work)
    jobs = []
    identity = None
    if cache_dir is not None:
        from selection import environment_identity
        from general_env import sha
        identity = {'environment':environment_identity(), 'screen_evaluator':sha(Path(__file__)),
                    'model':sha(Path(model)), 'steps':steps, 'total_steps':total_steps,
                    'epsilon':epsilon, 'data_role':'screen', 'version':1}

    def episode(index, seed):
        key, path, specification = None, None, None
        if identity is not None:
            specification = {**identity, 'seed':str(seed)}
            key = hashlib.sha256(json.dumps(specification,sort_keys=True).encode()).hexdigest()
            path = Path(cache_dir)/f'{key}.json'
            if path.exists():
                try:
                    cached = json.loads(path.read_text())
                    result = cached['result']
                    if (cached['identity'] == specification and has_episode_score(result)
                            and result.get('model_sha256') == identity['model']
                            and result.get('data_role') == 'screen'
                            and str(result.get('seed')) == str(seed)):
                        return {**result, 'policy_version':policy_version,
                                'cache_hit':True, 'cache_source':str(path)}
                except (ValueError, KeyError, TypeError):
                    pass
        result = run_episode(work / f"{policy_version}-{index}", seed, steps,
                             None, model, epsilon, None, policy_version, False, total_steps, data_role="screen")
        if path is not None and has_episode_score(result) and result.get('truncation_reason') != 'no_game_time_progress':
            storage.guard()
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False,suffix='.tmp') as stream:
                json.dump({'identity':specification,'result':result},stream)
            Path(stream.name).replace(path)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(6, len(seeds)))) as pool:
        for index, seed in enumerate(seeds):
            jobs.append(pool.submit(episode, index, seed))
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
              if has_episode_score(row)]
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
