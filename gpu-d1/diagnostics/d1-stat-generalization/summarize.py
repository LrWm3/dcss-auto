"""Per-configuration reports and paired map-cluster comparisons."""
import json
import numpy as np
import runtime as r


def aggregate(rows):
    n=sum(x['episodes'] for x in rows)
    return dict(episodes=n,exits=sum(x['exits'] for x in rows),deaths=sum(x['deaths'] for x in rows),timeouts=sum(x['timeouts'] for x in rows),
        exit_rate=sum(x['exits'] for x in rows)/n,worst_quartile_mean_exit=float(np.mean(sorted(x['exit_rate'] for x in rows)[:max(1,(len(rows)+3)//4)])),
        turns=float(np.mean([x['turns'] for x in rows])),rest_turns=float(np.mean([x['rest_turns'] for x in rows])))


def groups(rows):
    result={'all':rows}
    for key,pred in [('nominal',lambda p:p['id']==0),('seen_stats',lambda p:p['split']=='train'),('heldout_combinations',lambda p:p['split']=='test')]:
        sel=[x for x in rows if pred(r.SPEC['profiles'][x['profile']])]
        if sel:result[key]=sel
    return result


def paired(a,b):
    assert a['maps']==b['maps'] and a['seed']==b['seed'] and a['repeats']==b['repeats']
    result={}
    for name,rows in groups(a['profiles']).items():
        ids=[x['profile'] for x in rows];br={x['profile']:x for x in b['profiles']}
        delta=np.asarray([np.asarray(x['exits_by_map'])-np.asarray(br[x['profile']]['exits_by_map']) for x in rows])/a['repeats']
        per_map=delta.mean(0);n=len(per_map);rng=np.random.default_rng(997711)
        boot=per_map[rng.integers(0,n,(20000,n))].mean(1)
        result[name]=dict(delta_pp=float(100*delta.mean()),map_cluster_95_interval_pp=(100*np.quantile(boot,[.025,.975])).tolist(),configurations=len(ids),maps=n)
    return result


def main():
    result=json.loads((r.SUITE/'result.json').read_text())
    summary=dict(selection=result['selection'],training={},panels={},comparisons={},main_wall_seconds=result['wall_seconds'],preflight=json.loads((r.SUITE/'preflight.json').read_text()))
    for arm in ['fixed','varied']:
        curve=json.loads((r.SUITE/f'{arm}/curve.json').read_text())
        summary['training'][arm]=dict(decisions=curve[-1]['decisions'],training_seconds=curve[-1]['training_seconds'],physical_turns=curve[-1]['physical_turns'],
            completed_episodes=sum(curve[-1]['episode_histogram']),episode_histogram=curve[-1]['episode_histogram'],
            validation=[dict(decisions=x['decisions'],training_seconds=x['training_seconds'],**{m:{k:x[m][k] for k in ['exit_rate','death_rate','timeout_rate','turns']} for m in ['sampled','greedy']}) for x in curve])
    raw={}
    for path in sorted((r.SUITE/'eval').glob('*.json')):
        x=json.loads(path.read_text());raw[path.stem]=x
        summary['panels'][path.stem]=dict(split=x['split'],mode=x['mode'],seconds=x['seconds'],
            groups={name:aggregate(rows) for name,rows in groups(x['profiles']).items()},
            profiles=[{k:v for k,v in row.items() if not k.endswith('_by_map')} for row in x['profiles']])
    for panel,split in [('main','test'),('main','train'),('interpolation','test'),('extrapolation','test'),('nominal','test')]:
        for mode in ['sampled','greedy']:
            suffix=f'{panel}-{split}-{mode}'
            if 'varied-'+suffix not in raw:continue
            summary['comparisons'][suffix]={ref:paired(raw['varied-'+suffix],raw[ref+'-'+suffix]) for ref in ['source','fixed']}
    for mode in ['sampled','greedy']:
        summary['comparisons']['actual_vs_masked_stats-'+mode]=paired(raw[f'varied-main-test-{mode}'],raw[f'varied-masked-main-test-{mode}'])
    probe_path=r.SUITE/'probes/result.json'
    if probe_path.exists():
        p=json.loads(probe_path.read_text());summary['probes']=dict(states=len(p['rows']),seconds=p['seconds'],by_kind={},verified_improvable=sum(x['verified_better'] for x in p['verification']['reports']),caveat=p['caveat'])
        for kind in ['corridor','target_selection','sleep_rest']:
            ids=[i for i,x in enumerate(p['rows']) if x['kind']==kind]
            summary['probes']['by_kind'][kind]={name:dict(exit_rate=float(np.mean([model['rows'][i]['exit_rate'] for i in ids])),
                stat_mask_changes_greedy=sum(model['rows'][i]['action']!=model['rows'][i]['masked_action'] for i in ids)) for name,model in p['models'].items()}
        summary['probes']['per_state']=[dict(**row,verified=p['verification']['reports'][i],models={name:{k:v for k,v in model['rows'][i].items() if k not in ['state','probabilities','masked_probabilities']} for name,model in p['models'].items()}) for i,row in enumerate(p['rows'])]
    summary['caveats']=['One training seed; intervals describe map variation, not training-seed uncertainty.',
        'New spawn protocol, shared across arms; compare against the frozen source on this protocol, not earlier episode counts.',
        'Visible enemy stats are exact proxies. Hidden enemy count/strength are not exposed.',
        'Feature masking supplies misleading out-of-distribution inputs, not a separately trained feature ablation.']
    out=r.ROOT/'results/d1-stat-generalization.json';out.write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    if probe_path.exists():(r.ROOT/'results/d1-stat-generalization-probes.json').write_text(json.dumps(p,separators=(',',':'),allow_nan=False)+'\n')
    print(json.dumps(dict(selection=summary['selection'],training={k:{f:x[f] for f in ['decisions','training_seconds','physical_turns']} for k,x in summary['training'].items()},
        panels={k:x['groups'] for k,x in summary['panels'].items()},comparisons=summary['comparisons'],probes={k:v for k,v in summary.get('probes',{}).items() if k!='per_state'}),indent=2))

if __name__=='__main__':main()
