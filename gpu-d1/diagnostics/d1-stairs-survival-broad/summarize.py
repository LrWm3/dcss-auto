"""Compact full-floor and held-out-encounter comparisons for broader practice."""
import collections
import hashlib
import json
import numpy as np
import torch
import run


def practice_comparison(a,b):
    """Paired map bootstrap, retaining state weighting when maps have unequal counts."""
    assert a['state_ids']==b['state_ids'] and a['map_seeds']==b['map_seeds']
    delta=np.asarray(a['per_state_exit'])-np.asarray(b['per_state_exit'])
    maps=np.asarray(a['map_seeds']);unique=np.unique(maps)
    sums=np.asarray([delta[maps==m].sum() for m in unique])
    counts=np.asarray([(maps==m).sum() for m in unique])
    draws=np.random.default_rng(840311).integers(0,len(unique),(20000,len(unique)))
    boot=sums[draws].sum(1)/counts[draws].sum(1)
    return dict(delta_pp=float(100*delta.mean()),maps=len(unique),
        map_cluster_95_interval_pp=(100*np.quantile(boot,[.025,.975])).tolist(),
        improved_states=int((delta>0).sum()),worsened_states=int((delta<0).sum()),
        unchanged_states=int((delta==0).sum()))


@torch.no_grad()
def main():
    torch.set_num_threads(1)
    r=json.loads((run.SUITE/'result.json').read_text())
    summary=dict(selected_decisions=r['selected_decisions'],comparisons=r['comparisons'],
        full_floors={},practice=r['practice'],data={},training_seconds=r['curve'][-1]['training_seconds'],
        physical_turns=r['curve'][-1]['physical_turns'],practice_decisions=r['curve'][-1]['practice_decisions'],
        wall_seconds=r['wall_seconds'],validation=[])
    summary['practice_comparisons']={ref:{split:practice_comparison(r['practice']['broad'][split],r['practice'][ref][split])
        for split in ['train','heldout']} for ref in ['baseline','previous20','control']}
    layouts={}
    for split in ['train','validation','test']:
        hashes=set()
        for path in (run.core.CORPUS/split).glob('map-*.bin'):
            with path.open('rb') as f:
                f.seek(28);floor=f.read(5600)
            assert len(floor)==5600
            hashes.add(hashlib.sha256(floor).hexdigest())
        layouts[split]=hashes
    overlaps={a+'_'+b:len(layouts[a]&layouts[b]) for a,b in [('train','validation'),('train','test'),('validation','test')]}
    assert not any(overlaps.values()),'Terrain layout overlap'
    summary['layout_check']=dict(unique_layouts={k:len(v) for k,v in layouts.items()},overlaps=overlaps)
    for row in r['curve']:
        summary['validation'].append(dict(decisions=row['decisions'],training_seconds=row['training_seconds'],
            counts={m:{k:int(sum(row[m]['outcomes'][k])) for k in ['exit','death','timeout']} for m in ['sampled','greedy']}))
    for name,modes in r['confirmation'].items():
        summary['full_floors'][name]={}
        for mode,x in modes.items():
            b=r['confirmation']['baseline'][mode]['outcomes'];o=x['outcomes']
            summary['full_floors'][name][mode]=dict(episodes=x['episodes'],exit_rate=x['exit_rate'],turns=x['turns'],
                counts={k:int(sum(o[k])) for k in ['exit','death','timeout']},
                former_deaths_now_exit=int(sum(d and e for d,e in zip(b['death'],o['exit']))),
                new_deaths=int(sum(not d and e for d,e in zip(b['death'],o['death']))))
    for split,key in [('train','train'),('validation','heldout')]:
        bank=torch.load(run.SUITE/f'{split}-bank.pt',weights_only=False)
        labels=torch.load(run.SUITE/f'{split}-corrections.pt',weights_only=False)
        accepted=labels['ids'].tolist();actions=labels['actions'].tolist()
        summary['data'][key]=dict(deaths=bank['deaths'],states=len(bank['obs']),death_maps=len(bank['by_map']),
            verified_examples=len(accepted),verified_maps=len({bank['rows'][i]['map_seed'] for i in accepted}),
            accepted_offsets=dict(collections.Counter(bank['rows'][i]['offset'] for i in accepted)),
            accepted_death_timing=dict(collections.Counter(bank['rows'][i]['age'] for i in accepted)),
            action_types=dict(collections.Counter('move' if a<8 else 'attack' if a<16 else ['wait','rest','descend'][a-16] for a in actions)),
            collection_seconds=bank['seconds'],verification_seconds=labels['seconds'],collection_decisions=bank['collection_decisions'])
    audit_path=run.ROOT/'learning-runs/d1-stairs-deaths/snapshots.pt'
    if audit_path.exists():
        audit=torch.load(audit_path,weights_only=False);i=int(torch.where(audit['ids']==1607)[0].item())
        chosen=r['selected_decisions']
        paths=dict(baseline=run.core.SOURCE,previous20=run.PREVIOUS/'targeted/checkpoints/5000192.pt',
            broad=run.SUITE/f'targeted/checkpoints/{chosen}.pt' if chosen else run.core.SOURCE)
        model=run.core.load_model();summary['corridor_probe']={}
        probe=run.probe_library()
        corridor={k:audit[k][0,i:i+1] for k in ['state','obs','mask']}
        corridor['split']='test'
        for name,path in paths.items():
            model.load_state_dict(torch.load(path,map_location='cpu',weights_only=False)['model'])
            d=model(audit['obs'][0,i:i+1].cuda(),audit['mask'][0,i:i+1].cuda())[0]
            summary['corridor_probe'][name]=dict(greedy_action=int(d.greedy()[0]),move_e_probability=float(d.probs[0,1]),
                attack_nw_probability=float(d.probs[0,15]),note='Previously audited fatal state; unforced greedy continuation on 64 fresh RNGs; not a selection metric')
            out=run.futures(model,corridor,torch.zeros(64,dtype=torch.long),d.greedy().cpu().repeat(64),850311,probe)
            summary['corridor_probe'][name]['fresh_futures']={k:int(out[:,j].sum()) for j,k in enumerate(['exit','death','timeout'])}
        run.POOL.clear()
    (run.ROOT/'results/d1-stairs-survival-broad-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='practice'},indent=2))
    for model,rows in summary['practice'].items():
        print(model,{k:{f:x[f] for f in ['states','episodes','exits','deaths','timeouts','greedy_label_matches']} for k,x in rows.items()})


if __name__=='__main__':main()
