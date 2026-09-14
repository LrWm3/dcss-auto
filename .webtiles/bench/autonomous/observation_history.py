"""Bounded observed history, persisted in the checkpoint observation."""
def observed_displacement(before, action, after):
    p, q = before.get('player') or {}, after.get('player') or {}
    if all(k in p and k in q for k in ('x','y')):
        return q['x']-p['x'], q['y']-p['y']
    # Ordinary Lua may not expose absolute coordinates. Verify a displacement
    # against remembered terrain; don't assume a command moved the player.
    from structured_features import cell_map
    old, new = cell_map(before), cell_map(after)
    candidates = [(0,0)]
    if action.get('kind') == 'MOVE':
        candidates.append((action.get('dx',0),action.get('dy',0)))
    valid=[]
    for dx,dy in dict.fromkeys(candidates):
        comparisons=[(c.get('feature'),new[(x-dx,y-dy)].get('feature'))
                     for (x,y),c in old.items() if (x-dx,y-dy) in new and c.get('feature')]
        if len(comparisons)>=4 and all(a==b for a,b in comparisons):
            valid.append((dx,dy))
    return valid[0] if len(valid)==1 else None


def add_history(before, action, after):
    p, q = before.get('player') or {}, after.get('player') or {}
    enemies = before.get('monsters') or []
    enemies = list(enemies.values()) if isinstance(enemies, dict) else enemies
    same_level = before.get('level') == after.get('level')
    # Prefer measured displacement: blocked movement and forced relocation can
    # differ from the command. Positions are relative to the new player tile.
    displacement = observed_displacement(before,action,after) if same_level else None
    tracked = same_level and displacement is not None
    dx,dy = displacement or (0,0)
    record = {
        'action': dict(action),
        'hp_delta': q.get('hp',p.get('hp',0))-p.get('hp',0),
        'turn_delta': after.get('turn',0)-before.get('turn',0),
        'failed': (after.get('last_action_result') or {}).get('dispatch_accepted') is False,
        'last_seen_enemies': [{'name':m.get('name'), 'x':m.get('x',0)-dx,
                               'y':m.get('y',0)-dy} for m in enemies] if tracked else [],
        'position_tracking_available': tracked,
    }
    history = []
    if same_level:
        for old in before.get('history', [])[-3:]:
            old = {**old, 'last_seen_enemies': [
                {**m, 'x':m['x']-dx,'y':m['y']-dy} for m in old.get('last_seen_enemies',[])] if tracked else []}
            history.append(old)
    return {**after, 'history': history+[record]}
