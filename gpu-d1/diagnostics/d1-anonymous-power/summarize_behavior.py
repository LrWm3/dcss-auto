"""Compact, reproducible summary of behavior.py's ignored raw results."""
import json
import statistics as stats
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'learning-runs/d1-anonymous-power/behavior/result.json'
OUT = ROOT / 'results/d1-anonymous-power-behavior.json'


def summarize(d):
    result = {'seconds': d['seconds'], 'states': len(d['states']),
              'caveats': d['caveats'], 'matched': {}, 'damage_only_contrasts': {}}
    for context in ['sleeping', 'adjacent']:
        ids = [i for i, row in enumerate(d['states']) if row['context'] == context]
        target = result['matched'][context] = {}
        for model, initial in d['initial'].items():
            cell = target[model] = {'initial_mean': {
                key: stats.mean(initial[i][key] for i in ids)
                for key in ['move', 'attack', 'wait', 'rest', 'stair_move']}}
            cell['move_by_hp_fraction_and_profile'] = {
                str(hp): [stats.mean(initial[i]['move'] for i in ids
                                    if d['states'][i]['profile'] == p
                                    and d['states'][i]['hp_percent'] == hp)
                          for p in range(9)] for hp in [50, 100]}
            for mode in ['greedy', 'sampled']:
                r = d['rollouts'][model + '_' + mode]
                cell[mode] = {'episodes': len(ids) * r['repeats']}
                cell[mode].update({key: sum(r['rows'][i][key] for i in ids)
                                  for key in ['exits', 'deaths', 'timeouts', 'exit_without_kill']})
    lookup = {(x['context'], x['profile'], x['hp_percent'], x['geometry'], x['template']): i
              for i, x in enumerate(d['states'])}
    for low, high in [(1, 3), (4, 5)]:
        cell = result['damage_only_contrasts'][f'{low}_to_{high}'] = {}
        for model, initial in d['initial'].items():
            diffs = []
            for key, i in lookup.items():
                if key[0] == 'adjacent' and key[-1] == low:
                    j = lookup[key[:-1] + (high,)]
                    diffs.append(initial[j]['move'] - initial[i]['move'])
            cell[model] = {'pairs': len(diffs), 'mean_move_probability_change': stats.mean(diffs),
                           'minimum': min(diffs), 'maximum': max(diffs)}
    result['natural_stalls'] = {k: v for k, v in d['natural_stalls'].items()
                               if k != 'timeout_episode_rows'}
    result['stall_states'] = d['stall_states']
    result['stall_interventions'] = {}
    for key, r in d['stall_interventions'].items():
        cell = {'states': len(r['rows']), 'futures_per_state': r['repeats']}
        cell.update({k: sum(x[k] for x in r['rows']) for k in ['exits', 'deaths', 'timeouts']})
        result['stall_interventions'][key] = cell
    return result


if __name__ == '__main__':
    OUT.write_text(json.dumps(summarize(json.loads(RAW.read_text())), indent=2) + '\n')
    print(OUT)
