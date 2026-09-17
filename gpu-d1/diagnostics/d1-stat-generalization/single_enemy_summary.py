"""Compact checked-in report from the reproducible raw diagnostic output."""
import collections
import json
import runtime as r

def main():
    raw=json.loads((r.SUITE/'single-enemy/result.json').read_text());states=raw['states']
    agents={**raw['controllers'],**raw['models']}
    summary=dict(design=raw['design'],caveats=raw['caveats'],seconds=raw['seconds'],aggregates={},hard_cases={},nominal_and_hard={},first_choices={})
    def stats(rows,n):
        return dict(states=len(rows),episodes=len(rows)*n,**{k:sum(x[k] for x in rows)/len(rows) for k in ['exit','death','timeout','turns','kills','damage','return']})
    for name,data in agents.items():
        out={}
        for context in ['sleeping_edge','adjacent_awake']:
            for hp in [25,50,100]:
                rows=[x for x in data['rows'] if states[x['state']]['context']==context and states[x['state']]['hp_percent']==hp]
                if rows:out[f'{context}_hp{hp}']=stats(rows,data['repeats'])
        summary['aggregates'][name]=out
    fight=raw['controllers']['fight']
    for context in ['sleeping_edge','adjacent_awake']:
        for hp in [25,50,100]:
            rows=[x for x in fight['rows'] if states[x['state']]['context']==context and states[x['state']]['hp_percent']==hp]
            worst=sorted(rows,key=lambda x:(-x['death'],x['state']))[:12]
            summary['hard_cases'][f'{context}_hp{hp}']=[dict(**states[x['state']],**x) for x in worst]
    for profile_name,values in [('nominal',[18,4,1.,1.,24]),('weak_player_strong_enemies',[12,3,1.25,1.25,24]),('strong_player_weak_enemies',[24,5,.75,.75,24])]:
        profile=next(p['id'] for p in raw['profiles'] if p['values']==values)
        out={}
        for context in ['sleeping_edge','adjacent_awake']:
            for hp in [25,50,100]:
                for kind in range(6):
                    rows=[x for x in fight['rows'] if states[x['state']]['profile']==profile and states[x['state']]['context']==context and states[x['state']]['hp_percent']==hp and states[x['state']]['kind']==kind]
                    out[f'{context}_hp{hp}_kind{kind}']=stats(rows,fight['repeats'])
        summary['nominal_and_hard'][profile_name]=out
    for name,data in raw['models'].items():
        out={}
        for context in ['sleeping_edge','adjacent_awake']:
            for hp in [25,50,100]:
                rows=[x for x in data['rows'] if states[x['state']]['context']==context and states[x['state']]['hp_percent']==hp]
                counts=collections.Counter('move' if x['initial_action']<8 else 'attack' if x['initial_action']<16 else ['wait','rest','descend'][x['initial_action']-16] for x in rows)
                out[f'{context}_hp{hp}']=dict(initial_actions=dict(counts),**stats(rows,data['repeats']))
        # Identical geometry and enemy stats, only player damage changes.
        groups=collections.defaultdict(list)
        for x in data['rows']:
            s=states[x['state']];groups[(s['context'],s['geometry'],s['hp'],s['max_hp'],s['kind'],s['enemy_hp'],s['enemy_damage'])].append((s['player_damage'],x['initial_action']))
        groups=[v for v in groups.values() if len({a for a,b in v})==3]
        out['damage_sensitivity']=dict(groups=len(groups),groups_with_any_greedy_change=sum(len({b for a,b in v})>1 for v in groups))
        summary['first_choices'][name]=out
    # Count danger at a practical threshold. This is a descriptive screen,
    # not a multiplicity-adjusted declaration for every individual configuration.
    summary['danger_counts']={}
    for context in ['sleeping_edge','adjacent_awake']:
        for hp in [25,50,100]:
            rows=[x for x in fight['rows'] if states[x['state']]['context']==context and states[x['state']]['hp_percent']==hp]
            summary['danger_counts'][f'{context}_hp{hp}']=dict(states=len(rows),death_at_least_10pct=sum(x['death']>=.1 for x in rows),death_at_least_25pct=sum(x['death']>=.25 for x in rows),max_death=max(x['death'] for x in rows))
    dest=r.ROOT/'results/d1-single-enemy-danger.json';dest.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ['aggregates','danger_counts','first_choices']},indent=2))

if __name__=='__main__':main()
