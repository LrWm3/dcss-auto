"""Generate bootstrap or policy trajectories from real Crawl actors."""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from general_env import GeneralEnvironment
from policy import Policy
from teacher import choose_action
import storage


def _progression(state: dict) -> float:
    if state.get("terminal") == "death":
        return float(state.get("score") or 0)
    branch = str(state.get("branch", ""))
    branch_bonus = {"D": 0, "Lair": 100, "Orc": 180, "Swamp": 260,
                    "Shoals": 260, "Elf": 300, "Vaults": 400, "Depths": 500,
                    "Zot": 700, "Abyss": 200}.get(branch, 50)
    return branch_bonus + float(state.get("depth", 0)) * 10.0 + float(state.get("turn", 0)) / 10000.0


def run_episode(workspace: str | Path, seed: str, steps: int,
                replay_path: str | Path | None = None,
                model_path: str | Path | None = None, epsilon: float = 0.05,
                archive_dir: str | Path | None = None, policy_version: str = "teacher",
                snapshot: bool = True) -> dict:
    workspace = Path(workspace)
    if model_path and policy_version == "teacher":
        policy_version = Path(model_path).stem
    replay_path = Path(replay_path) if replay_path else None
    archive_dir = Path(archive_dir) if archive_dir else None
    if replay_path:
        replay_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_dir:
        archive_dir.mkdir(parents=True, exist_ok=True)
    env = GeneralEnvironment(workspace, seed=str(seed))
    rows = 0
    started = time.time()
    completed = False
    try:
        state = env.launch()
        archive_case = None
        if snapshot and archive_dir:
            # Saving is intentionally a separate engine boundary.  Restore the
            # fresh checkpoint before collecting, so the trajectory remains
            # contiguous while the exact RNG-preserving state is archived.
            archive_case = archive_dir / f"seed-{seed}-initial"
            if not archive_case.exists():
                env.save_state(archive_case)
                state = env.launch(archive_case)
        policy = None
        if model_path:
            policy, _ = Policy.from_checkpoint(model_path, epsilon=epsilon, seed=int(seed) & 0xFFFFFFFF)
        terminal = False
        captured = set()
        for step in range(steps):
            # Archive encountered combat/floor states, not just new-game starts.
            bucket = (state.get("level"), bool(state.get("monsters")))
            if archive_dir and snapshot and bucket not in captured and len(captured) < 4:
                captured.add(bucket)
                if step > 0:
                    target = archive_dir / f"seed-{seed}-turn-{state.get('turn')}-{policy_version}"
                    if not target.exists():
                        env.save_state(target)
                        state = env.launch(target)
            before = state
            teacher_index = choose_action(before)
            if policy:
                action_index, action = policy.choose(before)
            else:
                action_index = choose_action(before)
                action = before["actions"][action_index]
            state = env.step(action_index)
            row = {
                "type": "transition", "episode_seed": str(seed), "step": step,
                "policy_version": policy_version, "observation": before,
                "action": action, "action_index": action_index,
                "teacher_action_index": teacher_index,
                "next_observation": state, "reward": 0.0,
                "return": state.get("score") if state.get("terminal") else None,
                "terminal": bool(state.get("terminal")),
            }
            if replay_path:
                with replay_path.open("a") as stream:
                    stream.write(json.dumps(row, sort_keys=True) + "\n")
            rows += 1
            if state.get("terminal"):
                terminal = True
                break
        result = {
            "seed": str(seed), "steps": rows, "terminal": terminal,
            "terminal_kind": state.get("terminal"),
            "score": state.get("score") if terminal else None,
            "progression": _progression(state), "final_level": state.get("level"),
            "final_turn": state.get("turn"), "archive_case": str(archive_case) if archive_case else None,
            "policy_version": policy_version, "elapsed_seconds": time.time() - started,
            "work": str(env.work_path),
            "work_paths": [str(p) for p in env.works],
        }
        if replay_path:
            storage.guard()
            result_file = replay_path.with_suffix(".result.json")
            temporary = result_file.with_name(result_file.name + ".tmp")
            temporary.write_text(json.dumps(result) + "\n")
            temporary.replace(result_file)
        completed = True
        return result
    finally:
        env.close()
        if completed:
            if replay_path:
                storage.compress(replay_path)
            storage.finish_logs(env.works, redundant=bool(replay_path))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--epsilon", type=float, default=0.05)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_episode(
        workspace=args.workspace, seed=args.seed, steps=args.steps,
        replay_path=args.replay, model_path=args.model, epsilon=args.epsilon,
        archive_dir=args.archive), sort_keys=True))


if __name__ == "__main__":
    main()
