"""Observed, floor-local visit memory. No hidden map or novelty reward.

Coordinates are relative to the player; uncertain displacement discards memory
rather than inventing visits. Level changes start a new floor-local episode.
"""
import math


def known_count(state):
    return len(state.get('known') or {})


def initial(state):
    return {'version': 1, 'step': 0, 'tiles': {'0:0': [1, 0]},
            'known_max': known_count(state), 'since_discovery': 0, 'since_new_tile': 0}


def advance(before, action, after):
    from observation_history import observed_displacement
    if before.get('level') != after.get('level'):
        return initial(after)
    delta = observed_displacement(before, action, after)
    if delta is None:
        return initial(after)
    previous = before.get('visit_memory') or initial(before)
    step = previous['step'] + 1
    dx, dy = delta
    tiles = {}
    for key, value in previous['tiles'].items():
        x, y = map(int, key.split(':'))
        tiles[f'{x-dx}:{y-dy}'] = list(value)
    new_tile = '0:0' not in tiles
    # A visit means arrival, not repeated REST/attacks while occupying a tile.
    if delta != (0, 0):
        count = tiles.get('0:0', [0, 0])[0]
        tiles['0:0'] = [min(count + 1, 1000000), step]
    if len(tiles) > 4096:
        tiles = dict(sorted(tiles.items(), key=lambda pair: pair[1][1], reverse=True)[:4096])
    discovered = known_count(after) > previous['known_max']
    return {'version': 1, 'step': step, 'tiles': tiles,
            'known_max': max(known_count(after), previous['known_max']),
            'since_discovery': 0 if discovered else previous['since_discovery'] + 1,
            'since_new_tile': 0 if new_tile else previous['since_new_tile'] + 1}


def features(state, action):
    memory = state.get('visit_memory')
    if not memory:
        return [0.] * 8
    xy = (action.get('dx', 0), action.get('dy', 0)) if action.get('kind') == 'MOVE' else (0, 0)
    target = memory['tiles'].get(f'{int(xy[0])}:{int(xy[1])}')
    current = memory['tiles'].get('0:0', [0, 0])
    return [1., float(target is not None),
            min(1., math.log1p(target[0]) / 10) if target else 0.,
            min(1., (memory['step'] - target[1]) / 100) if target else 0.,
            min(1., math.log1p(current[0]) / 10),
            min(1., memory['since_discovery'] / 100),
            min(1., memory['since_new_tile'] / 100),
            min(1., len(memory['tiles']) / 1000)]
