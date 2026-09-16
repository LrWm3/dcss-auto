"""Summarize paired training and unchanged tactical probes, preserving all raw results."""
import json
import pathlib
ROOT=pathlib.Path(__file__).resolve().parents[3]

def main():
    suite=ROOT/'learning-runs/vision15-symmetry-30m'
    def read(p):return json.loads(p.read_text())
    result={'training':{},'tactics':{},'static':{}}
    for name in ['ordinary_d4','clumps_d4']:
        result['training'][name]=read(suite/'runs'/f'{name}-seed0'/'result.json')
    ordinary=read(ROOT/'learning-runs/vision15-seen-death4-30m/runs/tiles_seen_death4-seed0/result.json')
    mixed=read(ROOT/'learning-runs/vision15-clumps-30m/runs/clumps_third-seed0/result.json')
    result['training']['ordinary_original']=ordinary;result['training']['clumps_original']=mixed
    names=['hallway-retreat.json','hallway-six-retreat.json','diagonal-pocket-retreat.json','distant-pocket-4-retreat.json','distant-pocket-6-retreat.json']
    for name in names:
        old=read(ROOT/'results'/name);new=read(ROOT/'results'/('d4-'+name))
        for arm in ['hold_fight','retreat_fight']:
            assert old['arms'][arm]==new['arms'][arm],(name,arm,'control drift')
        cells={}
        for version,data in [('original',old),('d4',new)]:
            for arm,a in data['arms'].items():
                if arm in ['hold_fight','retreat_fight'] and version=='original':continue
                contact='pocket_contact_turns' if 'pocket_contact_turns' in a else 'protected_contact_turns'
                wait=contact.replace('contact','wait')
                total=sum(a[contact][16:20]) if contact in a else None
                cells[version+'_'+arm]=dict(tough12_win=sum(a['win'][16:20])/4,tough12_rotation_wins=a['win'][16:20],
                    tough12_unresolved=sum(a['unresolved'][16:20])/4,
                    tough12_reached=sum(a['reached_pocket'][16:20])/4 if 'reached_pocket' in a else None,
                    tough12_contact_wait_fraction=sum(a[wait][16:20])/total if total else None,
                    tough12_contact_wait_by_rotation=[a[wait][i]/a[contact][i] if a[contact][i] else None for i in range(16,20)] if total else None)
        result['tactics'][name]=cells
    for name in ['pocket-symmetry-4-mirror0.json','pocket-symmetry-4-mirror1.json','pocket-symmetry-6-mirror0.json','pocket-symmetry-6-mirror1.json']:
        old=read(ROOT/'results'/name);new=read(ROOT/'results'/('d4-'+name))
        assert old['arms']['retreat_fight']==new['arms']['retreat_fight'],(name,'control drift')
    for version in ['','d4-']:
        data=read(ROOT/'results'/f'{version}pocket-static-actions.json')
        result['static'][version or 'original']=dict(exact_observation_symmetry_verified=data['exact_observation_symmetry_verified'],cases=[c for c in data['cases'] if c['mirror']==0 and c['kind']==3 and c['player_hp']==12 and c['enemy_hp']=='full'])
    result['scripted_control_results_exact']=True
    (ROOT/'results/vision15-symmetry-comparison.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
    print('COMPARISON',flush=True)
    for name,data in result['training'].items():print(name,data['train_seconds'],data['final']['sampled']['clear_rate'],flush=True)
    for name,cells in result['tactics'].items():print(name,{k:round(v['tough12_win']*100,2) for k,v in cells.items() if k in ['original_ordinary','original_mixed','d4_ordinary','d4_mixed']},flush=True)
if __name__=='__main__':main()
