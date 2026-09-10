"""A deliberately small bootstrap controller.

This is only a data generator.  It is not used as the long-term policy and
contains no Crawl-specific action output layer: it chooses among the actions
enumerated by the environment.
"""
from __future__ import annotations


def _actions(state):
    actions = state.get("actions", [])
    if isinstance(actions, dict):
        return [actions[key] for key in sorted(actions, key=lambda x: int(x))]
    return list(actions)


def choose_action(state: dict) -> int:
    actions = _actions(state)
    if not actions:
        raise ValueError("state has no legal actions")
    monsters = list((state.get("monsters") or {}).values()) if isinstance(state.get("monsters"), dict) else state.get("monsters", [])
    player = state.get("player", {})
    hp = float(player.get("hp", 0))
    max_hp = max(1.0, float(player.get("max_hp", 1)))

    # Basic survival: heal before walking into an obvious bad state.
    if hp / max_hp < 0.45:
        for i, action in enumerate(actions):
            if action.get("kind") == "QUAFF" and any(word in action.get("item_name", "")
                                                      for word in ("heal", "curing", "ambrosia")):
                return i

    # Engage adjacent enemies through the ordinary movement/attack action.
    adjacent = [
        (i, action) for i, action in enumerate(actions)
        if action.get("kind") == "MELEE"
    ]
    if adjacent:
        # Prefer the closest/highest threat target, but keep this deterministic.
        return max(adjacent, key=lambda pair: (
            next((m.get("threat", 0) for m in monsters
                  if m.get("x") == pair[1].get("x") and m.get("y") == pair[1].get("y")), 0),
            -max(abs(pair[1].get("x", 0)), abs(pair[1].get("y", 0))),
        ))[0]

    # Approach the closest visible reachable enemy using the currently legal
    # ordinary movement actions.
    if monsters:
        target = min(monsters, key=lambda m: max(abs(m.get("x", 0)), abs(m.get("y", 0))))
        moves = [(i, a) for i, a in enumerate(actions) if a.get("kind") == "MOVE"]
        if moves:
            return min(moves, key=lambda pair: (
                max(abs(target.get("x", 0) - pair[1].get("dx", 0)),
                    abs(target.get("y", 0) - pair[1].get("dy", 0))),
                pair[0],
            ))[0]

    # Exploration: prefer a frontier-adjacent destination, then a stable legal
    # movement action.  The environment reevaluates this after every step.
    cells = state.get("known", {})
    for i, action in enumerate(actions):
        if action.get("kind") != "MOVE":
            continue
        key = f"{action.get('dx', 0)}:{action.get('dy', 0)}"
        if cells.get(key, {}).get("frontier"):
            return i
    for i, action in enumerate(actions):
        if action.get("kind") == "MOVE":
            return i
    for i, action in enumerate(actions):
        if action.get("kind") == "WAIT":
            return i
    return 0
