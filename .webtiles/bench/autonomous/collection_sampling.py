"""Bounded checkpoint sampling independent of a specific policy failure."""
def capture_reason(state, step, ordinary_saved=False, loop=False):
    if loop:
        return 'loop'
    if step >= 20 and not ordinary_saved and state.get('safe') and not state.get('monsters'):
        return 'ordinary_exploration'
    if step % 40 == 0:
        return 'periodic'
    return None


def select_snapshots(snapshots, terminal, decisions):
    if not snapshots:
        return []
    ordinary = next((s for s in snapshots if s['reason'] == 'ordinary_exploration'), snapshots[0])
    selected = [dict(ordinary)]
    last = dict(snapshots[-1])
    if last['path'] != ordinary['path']:
        selected.append(last)
    if terminal == 'death':
        selected[-1]['selection_reason'] = 'preceding_death'
        selected[-1]['decisions_before_death'] = decisions - selected[-1]['step']
    else:
        selected[-1]['selection_reason'] = selected[-1]['reason']
    return selected
