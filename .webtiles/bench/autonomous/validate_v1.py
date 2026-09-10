"""Real-engine correctness smoke test for the general environment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from general_env import GeneralEnvironment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    live = GeneralEnvironment(args.workspace / "live")
    try:
        initial = live.launch()
        kinds = {action["kind"] for action in initial["actions"]}
        required = {"MOVE", "WAIT", "USE_ABILITY"}
        missing = required - kinds
        if missing:
            raise AssertionError(f"missing required action kinds: {sorted(missing)}")
        wait = next(i for i, action in enumerate(initial["actions"])
                    if action["kind"] == "WAIT")
        after = live.step(wait)
        case = args.workspace / "checkpoint"
        live.save_state(case)
    finally:
        live.close()

    left = GeneralEnvironment(args.workspace / "left")
    right = GeneralEnvironment(args.workspace / "right")
    try:
        a = left.launch(case)
        b = right.launch(case)
        compare = (a["turn"], a["level"], a["player"], a["monsters"], a["inventory"], a["known"])
        compare_b = (b["turn"], b["level"], b["player"], b["monsters"], b["inventory"], b["known"])
        if compare != compare_b:
            raise AssertionError("restored observations differ")
        wait_a = next(i for i, action in enumerate(a["actions"])
                      if action["kind"] == "WAIT")
        next_a = left.step(wait_a)
        next_b = right.step(wait_a)
        if next_a["turn"] != next_b["turn"] or next_a["player"] != next_b["player"] \
                or next_a["monsters"] != next_b["monsters"]:
            raise AssertionError("identical restored RNG/action replay diverged")
        print(json.dumps({"ok": True, "action_kinds": sorted(kinds),
                          "initial_seq": initial["seq"], "after_turn": after["turn"],
                          "restored_turn": a["turn"], "replay_turn": next_a["turn"],
                          "checkpoint": str(case)}))
    finally:
        left.close(); right.close()


if __name__ == "__main__":
    main()
