"""Stable numeric encodings for variable Crawl state/action pairs."""
from __future__ import annotations

import hashlib
import math
from typing import Iterable

STATE_DIM = 192
ACTION_DIM = 96
FEATURE_VERSION = "general-features-v1"


def _hash(value: object, modulo: int) -> int:
    raw = str(value).encode("utf-8", "replace")
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "little") % modulo


def _put_hashed(out: list[float], value: object, weight: float = 1.0,
                offset: int = 48, width: int = STATE_DIM - 48) -> None:
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
    out = [0.0] * STATE_DIM
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
        _put_hashed(out, "monster:" + str(monster.get("type", monster.get("name", "unknown"))),
                    1.0 / max(1, len(monsters)))
        for spell in _values(monster.get("spells")):
            _put_hashed(out, "spell:" + str(spell), 0.25)
    for item in inventory:
        _put_hashed(out, "item:" + str(item.get("class", "unknown")), 0.25)
        _put_hashed(out, "itemname:" + str(item.get("name", "unknown")), 0.1)
    return [max(-10.0, min(10.0, float(x))) for x in out]


_KINDS = {name: index for index, name in enumerate((
    "MOVE", "MELEE", "WAIT", "TAKE_STAIRS_DOWN", "TAKE_STAIRS_UP",
    "USE_ABILITY", "FIRE", "QUAFF", "READ", "WIELD", "WEAR", "REMOVE",
    "CAST", "EVOKE", "PICKUP", "DROP",
))}


def action_features(state: dict, action: dict) -> list[float]:
    out = [0.0] * ACTION_DIM
    kind = str(action.get("kind", "UNKNOWN"))
    out[_KINDS.get(kind, len(_KINDS))] = 1.0
    out[16] = max(-1.0, min(1.0, _scalar(action.get("dx"))))
    out[17] = max(-1.0, min(1.0, _scalar(action.get("dy"))))
    out[18] = max(-1.0, min(1.0, _scalar(action.get("x")) / 8.0))
    out[19] = max(-1.0, min(1.0, _scalar(action.get("y")) / 8.0))
    out[20] = _scalar(action.get("slot")) / 52.0
    out[21] = _scalar(action.get("quantity")) / 20.0
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
            out[32 + _hash(value, ACTION_DIM - 32)] += 1.0
    return [max(-10.0, min(10.0, float(x))) for x in out]


def pair_features(state: dict, action: dict) -> list[float]:
    return state_features(state) + action_features(state, action)
