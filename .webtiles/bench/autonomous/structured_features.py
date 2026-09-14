"""V6: explicit player-relative geometry, entities, effects, and history.

No game seed, RNG, hidden monster data, or training return enters this encoder.
Text uses bounded UTF-8 bytes, with an overflow bit, never hash buckets.
Unknown/missing properties have separate presence bits.
"""
import json
import math
import os

FEATURE_VERSION = 'general-features-v6-spatial-entities'
HEALTH_FEATURES = os.environ.get('DCSS_HEALTH_FEATURES') == '1'
if HEALTH_FEATURES:
    FEATURE_VERSION += '-health-v1'
REST_ONLY = os.environ.get('DCSS_REST_ONLY') == '1'
if REST_ONLY:
    FEATURE_VERSION += '-rest-v1'
VISIT_MEMORY = os.environ.get('DCSS_VISIT_MEMORY') == '1'
if VISIT_MEMORY:
    FEATURE_VERSION += '-visits-v1'

def health_features(player):
    hp, maximum = player.get('hp'), player.get('max_hp')
    if hp is None or maximum is None or number(maximum)<=0:
        return [0.,0.,0.,0.]
    missing=max(0.,number(maximum)-number(hp))
    return [1.,float(missing==0),missing/max(1.,number(maximum)),min(10.,missing/200)]
RADIUS = 8
SIDE = 2 * RADIUS + 1
KINDS = ('MOVE', 'MELEE', 'WAIT', 'TAKE_STAIRS_DOWN', 'TAKE_STAIRS_UP',
         'USE_ABILITY', 'FIRE', 'QUAFF', 'READ', 'WIELD', 'WEAR', 'REMOVE',
         'CAST', 'EVOKE', 'PICKUP', 'DROP')
if REST_ONLY:
    KINDS = tuple('REST' if kind == 'WAIT' else kind for kind in KINDS)
SKILLS = ('Fighting', 'Short Blades', 'Long Blades', 'Axes', 'Maces & Flails',
          'Polearms', 'Staves', 'Ranged Weapons', 'Throwing', 'Armour', 'Dodging',
          'Stealth', 'Shields', 'Unarmed Combat', 'Spellcasting', 'Conjurations',
          'Hexes', 'Summonings', 'Necromancy', 'Translocations', 'Fire Magic',
          'Ice Magic', 'Air Magic', 'Earth Magic', 'Alchemy', 'Invocations',
          'Evocations', 'Shapeshifting')
STATUSES = ('berserk', 'confused', 'poison', 'liquid fire', 'slow', 'haste',
            'exhaust', 'invisib', 'flight', 'might', 'agility', 'resistan',
            'constrict', 'mesmeri', 'paraly', 'petrif', 'silenc', 'corrod',
            'drain', 'teleport', 'marked', 'net', 'web', 'weak')
EFFECTS = ('curing', 'heal wounds', 'haste', 'might', 'berserk', 'invisibility',
           'resistance', 'ambrosia', 'magic', 'lignification', 'cancellation',
           'teleport', 'blink', 'fear', 'fog', 'summon', 'immolat', 'poison',
           'curare', 'paraly', 'charm', 'mindburst', 'warp', 'acid', 'flame',
           'fire', 'cold', 'frost', 'ice', 'lightning', 'smite', 'confus',
           'slow', 'heal', 'drain', 'torment', 'dispel', 'dig', 'polymorph')
TERRAINS = ('floor', 'wall', 'door', 'shallow_water', 'deep_water', 'lava',
            'stone_stairs_up', 'stone_stairs_down', 'escape_hatch_up',
            'escape_hatch_down', 'enter_shop', 'altar', 'trap', 'portal',
            'enter_', 'exit_')
CLOUDS = ('steam', 'fire', 'poison', 'miasma', 'freezing', 'acid', 'smoke',
          'fog', 'rain', 'storm', 'spectral', 'mutagenic')
PLAYER = tuple((k, s) for k, s in (
    ('hp',200), ('max_hp',200), ('mp',100), ('max_mp',100), ('xl',27),
    ('ac',50), ('ev',50), ('sh',50), ('strength',40), ('intelligence',40),
    ('dexterity',40), ('gold',1000), ('piety',200), ('penance',200),
    ('willpower',200), ('res_fire',3), ('res_cold',3), ('res_poison',3),
    ('res_shock',3), ('res_corr',3), ('res_draining',3), ('see_invisible',1),
    ('flying',1), ('berserk',1), ('confused',1), ('poisoned',1), ('on_fire',1),
    ('piety_rank',6), ('hasted',1), ('slowed',1), ('exhausted',1), ('teleporting',1),
    ('anchored',1), ('invisible',1), ('mesmerised',1), ('petrifying',1),
    ('silencing',1), ('regenerating',1), ('mighty',1), ('caught',1)))
MONSTER = tuple((k,s) for k,s in (
    ('x',8), ('y',8), ('threat',3), ('damage_level',5), ('max_hp',200),
    ('ac',30), ('ev',30), ('wl',200), ('range',8), ('reach_range',8),
    ('res_fire',3), ('res_cold',3), ('res_poison',3), ('res_shock',3),
    ('res_corr',3), ('res_draining',3), ('reachable',1), ('is_unique',1),
    ('is_stationary',1), ('is_constricting_you',1)))
ITEM = tuple((k,s) for k,s in (
    ('equipped',1), ('plus',10), ('damage',30), ('accuracy',20), ('delay',20),
    ('ac',20), ('ev',20), ('quantity',30), ('is_ranged',1), ('identified',1),
    ('is_throwable',1), ('is_xp_evoker',1), ('reach_range',8), ('charges',20)))
CLASSES = ('weapon', 'armour', 'jewellery', 'potion', 'scroll', 'wand',
           'missile', 'book', 'miscellany', 'gold', 'food', 'orb', 'rune')


def values(obj):
    return list(obj.values()) if isinstance(obj, dict) else list(obj or [])


def number(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else 0.0
    except (TypeError, ValueError):
        return 0.0


def text(value):
    return (json.dumps(value, sort_keys=True) if isinstance(value, (dict, list))
            else str(value or '')).lower()


def bytes_features(value, width=32):
    raw = text(value).encode('utf8')
    return [b / 255 for b in raw[:width]] + [0.] * max(0, width-len(raw)) + [float(len(raw)>width)]


def fields(obj, spec):
    return [max(-10., min(10., number(obj.get(k))/scale)) for k,scale in spec] + [
        float(k in obj and obj[k] is not None) for k,_ in spec]


def flags(value, vocabulary):
    value = text(value)
    return [float(word in value) for word in vocabulary]


def monster_features(m):
    if not m:
        return [0.] * MONSTER_DIM
    return ([1.] + fields(m, MONSTER) + flags(m.get('status'), STATUSES)
            + flags(m.get('spells'), EFFECTS) + bytes_features(m.get('name'))
            + bytes_features(m.get('spells'), 96) + bytes_features(m.get('speed_description')))


MONSTER_DIM = 1 + 2*len(MONSTER) + len(STATUSES) + len(EFFECTS) + 33 + 97 + 33


def item_features(item):
    if not item:
        return [0.] * ITEM_DIM
    # Names/subtypes are the player-visible identity, including unidentified
    # appearances. Do not infer unidentified potion/scroll effects from internals.
    name = item.get('name', '')
    identified = item.get('identified') is True
    return ([1.] + fields(item, ITEM) + flags(item.get('class'), CLASSES)
            + flags(name if identified else '', EFFECTS) + bytes_features(name, 64)
            + bytes_features(item.get('subtype') if identified else '', 32))


ITEM_DIM = 1 + 2*len(ITEM) + len(CLASSES) + len(EFFECTS) + 65 + 33
CELL_DIM = 9 + len(TERRAINS) + 1 + len(CLOUDS) + 1
GRID_CHANNELS = CELL_DIM + MONSTER_DIM + 4
GRID_DIM = SIDE*SIDE*GRID_CHANNELS
INVENTORY_SLOTS = 52
INVENTORY_DIM = INVENTORY_SLOTS*ITEM_DIM


def cell_map(state):
    result = {}
    for group in ('known', 'cells'):
        collection = state.get(group) or {}
        for key, cell in (collection.items() if isinstance(collection, dict)
                          else ((None, c) for c in collection)):
            if 'x' in cell and 'y' in cell:
                xy = (int(number(cell['x'])), int(number(cell['y'])))
            elif isinstance(key, str) and ':' in key:
                xy = tuple(map(int, key.split(':')))
            else:
                continue
            result[xy] = {**result.get(xy, {}), **cell}
    return result


def cell_features(cell):
    terrain = flags(cell.get('feature'), TERRAINS)
    cloud = flags(cell.get('cloud'), CLOUDS)
    return ([float(bool(cell))] + [float(bool(cell.get(k))) for k in
            ('visible','mapped','traversable','frontier','excluded','unsafe',
             'invisible_monster','occupied')] + terrain + [float(bool(cell.get('feature')) and not any(terrain))]
            + cloud + [float(bool(cell.get('cloud')) and not any(cloud))])


def global_features(state):
    p = state.get('player') or {}
    cells = cell_map(state)
    outside = [c for (x,y),c in cells.items() if max(abs(x),abs(y)) > RADIUS]
    inventory = values(state.get('inventory'))
    result = fields(p, PLAYER)
    result += [number(p.get('hp'))/max(1,number(p.get('max_hp'))),
               number(p.get('mp'))/max(1,number(p.get('max_mp'))),
               number(state.get('depth'))/27, number(state.get('turn'))/10000,
               float(bool(state.get('safe'))), len(outside)/1000,
               sum(bool(c.get('frontier')) for c in outside)/100,
               float(len(inventory)>INVENTORY_SLOTS)]
    for value in (state.get('branch'), state.get('level'), p.get('species'),
                  p.get('class'), p.get('god'), p.get('transform')):
        result += bytes_features(value)
    result += flags([state.get('status'), p.get('status')], STATUSES)
    result += fields(p.get('skills') or {}, [(s,27) for s in SKILLS])
    result += bytes_features(p.get('spells'),128)
    result += bytes_features(p.get('durations'),128)
    result += bytes_features(p.get('abilities'),128)
    if HEALTH_FEATURES:
        result += health_features(p)
    result += [float('history' in state)]
    history = state.get('history') or []
    for i in range(4):
        h = history[-4+i] if len(history) >= 4-i else {}
        a = h.get('action') or {}
        result += [float(bool(h))] + [float(a.get('kind') == kind) for kind in KINDS]
        result += [number(a.get('dx'))/8, number(a.get('dy'))/8,
                   number(h.get('hp_delta'))/100, number(h.get('turn_delta'))/10,
                   float(bool(h.get('failed'))),float(bool(h.get('position_tracking_available')))]
        result += bytes_features(h.get('last_seen_enemies'),128)
    return result


GLOBAL_DIM = len(global_features({}))
STATE_DIM = GLOBAL_DIM + GRID_DIM + INVENTORY_DIM


def state_features(state):
    if state.get('schema') != 'crawl-general-v1':
        raise ValueError('unsupported observation schema')
    result = global_features(state)
    cells = cell_map(state)
    monsters = {(int(number(m.get('x'))), int(number(m.get('y')))): m
                for m in values(state.get('monsters'))}
    history_positions = [{(int(number(m.get('x'))),int(number(m.get('y'))))
                          for m in h.get('last_seen_enemies',[])}
                         for h in (state.get('history') or [])[-4:]]
    history_positions = [set()]*(4-len(history_positions)) + history_positions
    for y in range(-RADIUS,RADIUS+1):
        for x in range(-RADIUS,RADIUS+1):
            result += cell_features(cells.get((x,y),{})) + monster_features(monsters.get((x,y)))
            result += [float((x,y) in positions) for positions in history_positions]
    slots = {int(number(i['slot'])):i for i in values(state.get('inventory')) if i.get('slot') is not None}
    for slot in range(INVENTORY_SLOTS):
        result += item_features(slots.get(slot))
    return result


def action_features(state, action, routes=None):
    from teacher import navigation_distances
    kind = action.get('kind')
    dx,dy = number(action.get('dx')),number(action.get('dy'))
    xy = (int(dx),int(dy)) if kind in ('MOVE','MELEE') else (0,0)
    target_xy = ((number(action['x']),number(action['y']))
                 if action.get('x') is not None and action.get('y') is not None else None)
    target = next((m for m in values(state.get('monsters'))
                   if target_xy == (number(m.get('x')),number(m.get('y')))),None)
    if os.environ.get('DCSS_TARGET_DETAILS') == '1' and target is None:
        target = action.get('target')
    item = next((i for i in values(state.get('inventory'))
                 if action.get('slot') is not None and str(i.get('slot')) == str(action['slot'])),None)
    if kind == 'PICKUP':
        item = next((i for i in values(state.get('floor_items'))
                     if i.get('name') == action.get('item_name')), None)
    result = [float(kind==k) for k in KINDS] + [float(kind not in KINDS)]
    result += [dx/8,dy/8,number(action.get('x'))/8,number(action.get('y'))/8,
               float(target_xy is not None),number(action.get('quantity'))/30]
    routes = routes if routes is not None else [navigation_distances(state,s) for s in (False,True)]
    for distances in routes:
        origin,dest = distances.get((0,0)),distances.get(xy)
        result += [float(dest is not None),float(origin is not None),
                   0. if dest is None or origin is None else max(-1.,min(1.,origin-dest))]
    result += cell_features(cell_map(state).get(xy,{}))
    result += monster_features(target) + item_features(item)
    result += flags(action.get('name'), EFFECTS) + bytes_features(action.get('name'),64)
    if VISIT_MEMORY:
        from visit_memory import features
        result += features(state, action)
    return result


ACTION_DIM = len(KINDS)+1+6+6+CELL_DIM+MONSTER_DIM+ITEM_DIM+len(EFFECTS)+65
if VISIT_MEMORY:
    ACTION_DIM += 8
