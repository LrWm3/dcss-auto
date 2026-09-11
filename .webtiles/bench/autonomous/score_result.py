"""A scored episode may finish naturally or at a declared administrative limit."""
import math


def has_episode_score(row):
    score = row.get("score")
    return ("error" not in row and isinstance(score, (int, float))
            and math.isfinite(score) and score >= 0
            and (bool(row.get("terminal")) or (
                bool(row.get("truncated")) and row.get("score_status") == "cutoff_official")))
