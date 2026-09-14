"""Generate bootstrap or policy trajectories from real Crawl actors."""
from __future__ import annotations
from exploration_score import learning_score, report_fields

import argparse
import json
import random
import time
import itertools
from collections import Counter
from pathlib import Path

from general_env import GeneralEnvironment, ENGINE, HERE, sha
from policy import Policy
from model import action_scores
from teacher import choose_action
import storage
from episode_budget import DecisionBudget
from data_split import assert_training_seed


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
                snapshot: bool = True, total_steps: int = 100000,
                no_turn_limit: int = 16, data_role: str = "training",
                exploration_seed: int | None = None) -> dict:
    if data_role == "training":
        assert_training_seed(seed)
    elif replay_path is not None or archive_dir is not None:
        raise ValueError("held-out evaluation cannot write training replay/archive")
    workspace = Path(workspace)
    if model_path and policy_version == "teacher":
        policy_version = Path(model_path).stem
    replay_path = Path(replay_path) if replay_path else None
    archive_dir = Path(archive_dir) if archive_dir else None
    if replay_path:
        replay_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_dir:
        archive_dir.mkdir(parents=True, exist_ok=True)
    env = GeneralEnvironment(workspace, seed=str(seed), data_role=data_role)
    # Replay already retains complete transitions. Failed/partial replay is
    # quarantined by the orchestrator; don't serialize a second full copy.
    env.record_events = replay_path is None
    rows = 0
    started = time.time()
    completed = False
    budget = DecisionBudget(steps, total_steps, no_turn_limit)
    replay_stream = None
    try:
        if replay_path:
            replay_stream = replay_path.open('a', buffering=65536)
        state = env.launch()
        archive_case = None
        if snapshot and archive_dir:
            # Snapshot at a decision boundary. New engines continue in place;
            # historical engines retain their explicit save/relaunch fallback.
            archive_case = archive_dir / f"seed-{seed}-engine-{sha(ENGINE)[:12]}-bridge-{sha(HERE / 'general_bridge.lua')[:12]}-initial"
            if not archive_case.exists():
                saved = env.save_state(archive_case)
                if saved.get('save_mode') != 'in_place':
                    state = env.launch(archive_case)
        policy = None
        if model_path:
            policy, _ = Policy.from_checkpoint(model_path, epsilon=epsilon,
                seed=exploration_seed if exploration_seed is not None else int(seed) & 0xFFFFFFFF)
        terminal = False
        captured = set()
        floor_captures = {}
        last_archived = None
        previous_combat = False
        action_counts = Counter()
        exploratory_steps = Counter()
        teacher_agreements = 0
        for step in itertools.count():
            if budget.reason(state):
                break
            # Archive encountered combat/floor states, not just new-game starts.
            # Keep collecting on later floors, and periodically within combat;
            # the old first-four-buckets cap excluded essentially all late play.
            visible_monsters = state.get('monsters') or []
            if isinstance(visible_monsters, dict):
                visible_monsters = list(visible_monsters.values())
            combat = bool(visible_monsters)
            encounter_start = combat and not previous_combat
            hp_fraction = state.get('player', {}).get('hp', 1) / max(
                1, state.get('player', {}).get('max_hp', 1))
            categories = []
            if encounter_start:
                categories.append('encounter_start')
            if hp_fraction < .35:
                categories.extend(['danger', 'death_adjacent'])
            elif not combat:
                categories.append('healthy')
            known_cells = state.get('known') or {}
            if isinstance(known_cells, dict):
                known_cells = known_cells.values()
            if any(c.get('frontier') for c in known_cells):
                categories.append('frontier')
            if policy and len(state.get('actions', [])) > 1:
                scores = action_scores(policy.model, state, state['actions'])
                ranked = list(reversed(scores.argsort().tolist()))
                if len(ranked) > 1 and float(scores[ranked[0]] - scores[ranked[1]]) < .10:
                    categories.append('uncertain')
            if not categories:
                categories.append('coverage')
            bucket = (state.get("level"), combat,
                      step // 100 if state.get("monsters") else 0,
                      hp_fraction < .5, tuple(categories))
            if (archive_dir and snapshot and bucket not in captured and len(captured) < 128
                    and floor_captures.get(state.get('level'), 0) < 8
                    and (floor_captures.get(state.get('level'), 0) < 6 or encounter_start)):
                captured.add(bucket)
                floor_captures[state.get('level')] = floor_captures.get(state.get('level'), 0) + 1
                if step > 0:
                    target = archive_dir / f"seed-{seed}-engine-{sha(ENGINE)[:12]}-bridge-{sha(HERE / 'general_bridge.lua')[:12]}-turn-{state.get('turn')}-{policy_version}"
                    if not target.exists():
                        saved = env.save_state(target)
                        if saved.get('save_mode') != 'in_place':
                            state = env.launch(target)
                    last_archived = target
                    (target / 'sampling.json').write_text(json.dumps({
                        'category': categories[0], 'categories': categories,
                        'step': step, 'level': state.get('level'),
                        'hp_fraction': hp_fraction,
                        'visible_monsters': len(visible_monsters),
                        'max_threat': max((m.get('threat', 0) for m in visible_monsters),
                                          default=0)}))
            previous_combat = combat
            before = state
            teacher_index = choose_action(before) if replay_path or not policy else None
            if policy:
                action_index, action = policy.choose(before, teacher_index=teacher_index)
                exploratory_steps[policy.last_exploration_mode] += 1
                teacher_agreements += int(teacher_index is not None and action_index == teacher_index)
            else:
                action_index = teacher_index
                action = before["actions"][action_index]
            action_counts[str(action.get("kind", "UNKNOWN"))] += 1
            state = env.step(action_index)
            budget.record(before, state)
            row = {
                "type": "transition", "episode_seed": str(seed), "step": step,
                "data_role": data_role,
                "exploration_seed": exploration_seed,
                "policy_version": policy_version, "observation": before,
                "action": action, "action_index": action_index,
                "teacher_action_index": teacher_index,
                "behavior_probability": policy.last_action_probability if policy else 1.0,
                "score_before": before.get("score") if before.get("score_status") == "live_official" else None,
                "score_after": state.get("score") if state.get("score_status") == "live_official" else None,
                "training_score_before": before.get("training_score"),
                "training_score_after": state.get("training_score"),
                **report_fields(state),
                "turn_before": before.get("turn"), "turn_after": state.get("turn"),
                "next_observation": state, "reward": 0.0,
                "return": learning_score(state) if state.get("terminal") else None,
                "terminal": bool(state.get("terminal")),
            }
            if replay_stream:
                replay_stream.write(json.dumps(row, sort_keys=True) + "\n")
            rows += 1
            if state.get("terminal"):
                terminal = True
                break
        truncation = budget.reason(state) if not terminal else None
        resume_checkpoint = None
        if truncation:
            resume_checkpoint = workspace / "truncations" / f"seed-{seed}-{time.time_ns()}"
            env.save_state(resume_checkpoint)
        result = {
            "seed": str(seed), "steps": rows, "terminal": terminal,
            "exploration_seed": exploration_seed,
            "model_sha256": sha(Path(model_path)) if model_path else None,
            "data_role": data_role,
            "terminal_kind": state.get("terminal"),
            "truncated": bool(truncation), "truncation_reason": truncation,
            "resume_checkpoint": str(resume_checkpoint) if resume_checkpoint else None,
            "decision_budget": budget.summary(),
            "score": state.get("score") if terminal or (
                truncation and state.get("score_status") == "live_official") else None,
            "score_status": "final_official" if terminal else (
                "cutoff_official" if truncation and state.get("score_status") == "live_official"
                else "unavailable"),
            **report_fields(state),
            "progression": _progression(state), "final_level": state.get("level"),
            "final_turn": state.get("turn"), "archive_case": str(archive_case) if archive_case else None,
            "policy_version": policy_version, "elapsed_seconds": time.time() - started,
            "action_counts": dict(action_counts),
            "exploration_counts": dict(exploratory_steps),
            "teacher_agreements": teacher_agreements,
            "work": str(env.work_path),
            "work_paths": [str(p) for p in env.works],
        }
        if replay_path:
            storage.guard()
            # Publish completion only after the buffered trajectory is closed.
            replay_stream.close()
            replay_stream = None
            result_file = replay_path.with_suffix(".result.json")
            temporary = result_file.with_name(result_file.name + ".tmp")
            temporary.write_text(json.dumps(result) + "\n")
            temporary.replace(result_file)
        if last_archived:
            (last_archived / 'outcome.json').write_text(json.dumps({
                'terminal': terminal, 'terminal_kind': state.get('terminal'),
                'final_turn': state.get('turn'), 'score': result['score']}))
        completed = True
        return result
    finally:
        if replay_stream:
            replay_stream.close()
        env.close()
        if completed:
            if replay_path:
                storage.compress(replay_path)
            storage.finish_logs(env.works, redundant=bool(replay_path))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--steps", "--decisions-per-floor", type=int, default=2000)
    parser.add_argument("--total-steps", type=int, default=100000)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--epsilon", type=float, default=0.05)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_episode(
        workspace=args.workspace, seed=args.seed, steps=args.steps,
        replay_path=args.replay, model_path=args.model, epsilon=args.epsilon,
        archive_dir=args.archive, total_steps=args.total_steps), sort_keys=True))


if __name__ == "__main__":
    main()
