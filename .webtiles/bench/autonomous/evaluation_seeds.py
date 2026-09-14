"""Deterministic, rotating held-out screen seeds."""
from __future__ import annotations

import json
from pathlib import Path

from data_split import SCREEN_PREFIX, held_out_seed

POOL_VERSION = "rotating-screen-pool-v1"


def _pool(size: int) -> list[str]:
    # C is reserved for screens; A is training, D confirmation, and E audit.
    return [str((SCREEN_PREFIX << 60) | index)
            for index in range(1, size + 1)]


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def screen_seed_plan(root, cycle: int, episodes: int, pool_size: int = 50):
    """Return a frozen rotating screen window and its manifest path.

    Five episodes per cycle over the default 50-seed pool covers every seed
    once in ten cycles, then repeats. Existing plans are immutable.
    """
    root = Path(root)
    cycle, episodes, pool_size = int(cycle), int(episodes), int(pool_size)
    if cycle < 0:
        raise ValueError("cycle must be non-negative")
    if pool_size < 1 or episodes < 1 or episodes > pool_size:
        raise ValueError("screen episodes must be between one and pool size")
    pool = _pool(pool_size)
    path = root / "evaluations" / "screen_seeds" / f"cycle-{cycle:04d}.json"
    start = (cycle * episodes) % pool_size
    seeds = [pool[(start + offset) % pool_size] for offset in range(episodes)]
    if not all(held_out_seed(seed) for seed in seeds):
        raise AssertionError("screen seed escaped held-out namespace")
    expected = {"version": POOL_VERSION, "cycle": cycle,
                "pool_size": pool_size, "episodes": episodes,
                "start_index": start, "seeds": seeds}
    if path.exists():
        if json.loads(path.read_text()) != expected:
            raise ValueError(f"frozen screen seed plan mismatch: {path}")
    else:
        _write(path, expected)
    return seeds, path
