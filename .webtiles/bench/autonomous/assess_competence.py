"""Paired fresh-game neural/random assessment; never used for fitting."""
import argparse
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from collections import Counter
import torch
from collect import run_episode
import storage


def trial(task):
    root, model, seed, steps, label = task
    torch.set_num_threads(1)
    replay = Path(root) / label / f"{seed}.jsonl"
    try:
        result = run_episode(replay.parent / str(seed), seed, steps, replay,
                             model, 1.0 if label == "random" else 0.0,
                             policy_version=label, snapshot=False)
        counts, levels = Counter(), set()
        with storage.open_text(replay.with_name(replay.name + ".gz")) as stream:
            for line in stream:
                row = json.loads(line)
                counts[row["action"]["kind"]] += 1
                levels.add(row["observation"]["level"])
        result.update(action_counts=dict(counts), levels=sorted(levels))
        return result
    except Exception as exc:
        return {"seed":seed,"policy_version":label,"error":repr(exc)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--steps", type=int, default=1200)
    p.add_argument("--seeds", nargs="+", default=["920000000001","920000000002","920000000003"])
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    tasks = [(str(args.output.resolve()), str(args.model.resolve()), seed,args.steps,label)
             for seed in args.seeds for label in ("neural","random")]
    results = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        for result in pool.map(trial,tasks):
            results.append(result)
            (args.output/"results.json").write_text(json.dumps(results,indent=2)+"\n")
            print(json.dumps(result),flush=True)
