"""Stable numeric encodings for variable Crawl state/action pairs."""
from __future__ import annotations

import hashlib
import math
from typing import Iterable

STATE_DIM = 448
ACTION_DIM = 160
FEATURE_VERSION = "general-features-v5-combat-properties"


def _hash(value: object, modulo: int) -> int:
    raw = str(value).encode("utf-8", "replace")
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "little") % modulo


def _put_hashed(out: list[float], value: object, weight: float = 1.0,
                offset: int = 48, width: int = 192 - 48) -> None:
    out[offset + _hash(value, width)] += weight


def _values(value):
    return list(value.values()) if isinstance(value, dict) else list(value or [])


def _scalar(value, default=0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else float(default)
    except (TypeError, ValueError):
        return float(default)


def state_features(state: dict) -> list[float]:
    if state.get("schema") != "crawl-general-v1":
        raise ValueError("unsupported observation schema")
    player = state.get("player", {})
    hp = _scalar(player.get("hp", state.get("hp", [0, 1])[0] if isinstance(state.get("hp"), list) else 0))
    max_hp = max(1.0, _scalar(player.get("max_hp", 1)))
    mp = _scalar(player.get("mp", 0))
    max_mp = max(1.0, _scalar(player.get("max_mp", 1)))
    monsters = _values(state.get("monsters"))
    inventory = _values(state.get("inventory"))
    actions = _values(state.get("actions"))
    threats = [_scalar(monster.get("threat")) for monster in monsters]
    distances = [max(abs(_scalar(monster.get("x"))), abs(_scalar(monster.get("y"))))
                 for monster in monsters]
    out = [0.0] * 192
    numeric = [
        hp / max_hp, mp / max_mp, _scalar(player.get("xl")) / 27.0,
        _scalar(player.get("ac")) / 50.0, _scalar(player.get("ev")) / 50.0,
        _scalar(player.get("sh")) / 50.0, _scalar(player.get("strength")) / 40.0,
        _scalar(player.get("intelligence")) / 40.0, _scalar(player.get("dexterity")) / 40.0,
        _scalar(state.get("depth")) / 27.0, _scalar(state.get("turn")) / 10000.0,
        len(monsters) / 20.0, max(threats, default=0.0) / 3.0,
        min(distances, default=20.0) / 20.0, sum(t >= 2 for t in threats) / 10.0,
        sum(t >= 3 for t in threats) / 10.0, len(inventory) / 50.0,
        len(actions) / 88.0, sum(1 for x in actions if x.get("kind") == "USE_ABILITY") / 10.0,
        sum(1 for x in actions if x.get("kind") == "FIRE") / 10.0,
        sum(1 for x in actions if x.get("kind") == "QUAFF") / 10.0,
        sum(1 for x in actions if x.get("kind") == "TAKE_STAIRS_DOWN"),
        sum(1 for x in actions if x.get("kind") == "TAKE_STAIRS_UP"),
        float(bool(player.get("confused"))), float(bool(player.get("berserk"))),
        float(bool(state.get("safe"))), float("liquid fire" in str(state.get("status", "")).lower()),
        float(any(c.get("frontier") for c in _values(state.get("known")))),
        float(any(c.get("cloud") for c in _values(state.get("cells")))),
        float(any(c.get("invisible_monster") for c in _values(state.get("cells")))),
        float(hp >= max_hp), float(bool(monsters)),
    ]
    for index, value in enumerate(numeric):
        out[index] = max(-10.0, min(10.0, value))
    for key in ("branch", "level", player.get("species"), player.get("class"),
                player.get("status"), state.get("status")):
        if key:
            _put_hashed(out, key)
    for skill, value in (player.get("skills") or {}).items():
        _put_hashed(out, "skill:" + skill, max(0.0, min(2.0, _scalar(value) / 27.0)))
    for monster in monsters:
        _put_hashed(out, ("monster-position", monster.get("name"),
                         monster.get("x"), monster.get("y")), 0.5)
        _put_hashed(out, "monster:" + str(monster.get("type", monster.get("name", "unknown"))),
                    1.0 / max(1, len(monsters)))
        for spell in _values(monster.get("spells")):
            _put_hashed(out, "spell:" + str(spell), 0.25)
    for item in inventory:
        _put_hashed(out, "item:" + str(item.get("class", "unknown")), 0.25)
        _put_hashed(out, "itemname:" + str(item.get("name", "unknown")), 0.1)
    for cell in _values(state.get("cells")):
        _put_hashed(out, ("terrain", cell.get("x"), cell.get("y"),
                         cell.get("feature"), cell.get("cloud")), 0.1)
    extra = [_scalar(player.get(k)) / scale for k, scale in PLAYER_FIELDS]
    extra += [_scalar(player.get('max_hp')) / 200, _scalar(player.get('max_mp')) / 100]
    equipped = [i for i in inventory if i.get('equipped')]
    for cls in ('weapon', 'armour', 'jewellery'):
        selected = [i for i in equipped if cls in str(i.get('class',''))]
        extra += [sum(item_properties(i)[j] for i in selected) for j in range(10)]
    ordered = sorted(monsters, key=lambda m: (max(abs(m.get('x',0)),abs(m.get('y',0))),
                                            m.get('y',0),m.get('x',0)))
    for i in range(8):
        extra += monster_properties(ordered[i]) if i < len(ordered) else [0.0]*24
    extra += [float(len(monsters)>8)]
    out += extra + [0.0] * (STATE_DIM-192-len(extra))
    return [max(-10.0, min(10.0, float(x))) for x in out]


_KINDS = {name: index for index, name in enumerate((
    "MOVE", "MELEE", "WAIT", "TAKE_STAIRS_DOWN", "TAKE_STAIRS_UP",
    "USE_ABILITY", "FIRE", "QUAFF", "READ", "WIELD", "WEAR", "REMOVE",
    "CAST", "EVOKE", "PICKUP", "DROP",
))}


def action_features(state: dict, action: dict, routes=None) -> list[float]:
    out = [0.0] * ACTION_DIM
    kind = str(action.get("kind", "UNKNOWN"))
    out[_KINDS.get(kind, len(_KINDS))] = 1.0
    out[16] = max(-1.0, min(1.0, _scalar(action.get("dx"))))
    out[17] = max(-1.0, min(1.0, _scalar(action.get("dy"))))
    out[18] = max(-1.0, min(1.0, _scalar(action.get("x")) / 8.0))
    out[19] = max(-1.0, min(1.0, _scalar(action.get("y")) / 8.0))
    out[20] = _scalar(action.get("slot")) / 52.0
    out[21] = _scalar(action.get("quantity")) / 20.0
    # Candidate-relative geometry exposes route costs without choosing a move.
    from teacher import navigation_distances
    destination = (action.get("dx", 0), action.get("dy", 0))
    for i, stairs in enumerate((False, True)):
        distances = routes[i] if routes is not None else navigation_distances(state, stairs)
        distance = distances.get(destination)
        origin = distances.get((0,0))
        out[26+i] = (0.0 if distance is None or origin is None
                     else max(-1.0,min(1.0,origin-distance)))
        out[28+i] = float(distance is not None)
    cell = (state.get("known") or {}).get(f"{destination[0]}:{destination[1]}", {})
    out[30] = float(bool(cell.get("cloud")))
    out[31] = float(bool(cell.get("frontier")))
    target = next((m for m in _values(state.get("monsters"))
                   if _scalar(m.get("x")) == _scalar(action.get("x"))
                   and _scalar(m.get("y")) == _scalar(action.get("y"))), None)
    if target:
        out[22] = _scalar(target.get("threat")) / 3.0
        out[23] = float(bool(target.get("reachable")))
        out[24] = max(abs(_scalar(target.get("x"))), abs(_scalar(target.get("y")))) / 20.0
        out[25] = _scalar(target.get("range"), 1.0) / 8.0
    for index, value in enumerate((action.get("name"), action.get("item_name"),
                                   action.get("target_name"), action.get("label"))):
        if value:
            out[32 + _hash(value, 96 - 32)] += 1.0
    out[96:120] = monster_properties(target) if target else [0.0]*24
    item = next((i for i in _values(state.get('inventory'))
                 if action.get('slot') is not None and i.get('slot') == action['slot']), None)
    out[120:130] = item_properties(item) if item else [0.0]*10
    actual_cell = (state.get('cells') or {}).get(f"{destination[0]}:{destination[1]}", {})
    for i, name in enumerate(('steam','fire','poison','miasma','freezing','acid')):
        out[130+i] = float(name in str(actual_cell.get('cloud','')).lower())
    return [max(-10.0, min(10.0, float(x))) for x in out]


PLAYER_FIELDS = [(k, s) for k, s in (
    ('res_fire',3),('res_cold',3),('res_poison',3),('res_shock',3),('res_corr',3),
    ('res_draining',3),('willpower',200),('poisoned',1),('on_fire',1),
    ('flying',1),('see_invisible',1),('berserk',1),('confused',1),('safe',1))]


def item_properties(item):
    return [float(bool(item.get('equipped'))), _scalar(item.get('plus'))/10,
            _scalar(item.get('damage'))/30, _scalar(item.get('accuracy'))/20,
            _scalar(item.get('delay'))/20, _scalar(item.get('ac'))/20,
            _scalar(item.get('ev'))/20, _scalar(item.get('quantity'))/30,
            float(bool(item.get('is_ranged'))), float(bool(item.get('identified')))]


def monster_properties(m):
    numeric = [('x',8),('y',8),('threat',3),('damage_level',5),('ac',30),('ev',30),
               ('wl',200),('range',8),('reach_range',8),('res_fire',3),('res_cold',3),
               ('res_poison',3),('res_shock',3),('res_corr',3),('res_draining',3)]
    values = [_scalar(m.get(k))/scale for k,scale in numeric]
    values += [float(bool(m.get(k))) for k in
               ('reachable','is_unique','is_stationary','is_constricting_you')]
    values += [float(k in str(m.get('status','')).lower()) for k in
               ('asleep','confused','invisible','berserk')]
    values += [float('faster' in str(m.get('speed_description','')))]
    return values


def pair_features(state: dict, action: dict) -> list[float]:
    return state_features(state) + action_features(state, action)
