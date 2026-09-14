"""A deliberately small bootstrap controller.

This is only a data generator.  It is not used as the long-term policy and
contains no Crawl-specific action output layer: it chooses among the actions
enumerated by the environment.
"""
from __future__ import annotations
from collections import deque


def navigation_distances(state, stairs=False):
    """Distances through remembered passable terrain to exploration goals."""
    cells = state.get("known") or {}
    cells = cells.values() if isinstance(cells, dict) else cells
    tiles = {(c["x"], c["y"]): c for c in cells if c.get("traversable")}
    goals = [p for p, c in tiles.items() if p != (0, 0) and (
        "stone_stairs_down" in c.get("feature", "") if stairs else c.get("frontier"))]
    distances = dict.fromkeys(goals, 0)
    queue = deque(goals)
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
            p = x+dx, y+dy
            if p in tiles and p not in distances:
                distances[p] = distances[(x,y)] + 1
                queue.append(p)
    return distances


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

    if hp < max_hp:
        for i, a in enumerate(actions):
            if a['kind'] in ('WAIT', 'REST'):
                return i
    for i, a in enumerate(actions):
        if a["kind"] == "TAKE_STAIRS_DOWN":
            return i
    for stairs in (False, True):
        distances = navigation_distances(state, stairs)
        moves = [(distances.get((a.get("dx"), a.get("dy")), float("inf")), i)
                 for i, a in enumerate(actions) if a["kind"] == "MOVE"]
        if moves and min(moves)[0] < float("inf"):
            return min(moves)[1]

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
        if action.get("kind") in ("WAIT", "REST"):
            return i
    return 0
