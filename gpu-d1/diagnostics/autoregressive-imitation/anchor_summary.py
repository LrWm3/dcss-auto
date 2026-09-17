"""Aggregate the predeclared three-seed policy-anchor comparison on test maps."""
import hashlib,json,pathlib
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[2]

def main():
    path=ROOT/'results/autoregressive-anchor-holdout.json';data=json.loads(path.read_text());r=data['results']
    names=['policy01-seed0','policy0.1-seed1','policy0.1-seed2']
    assert all(mode in r['navigation1-seed0'] for mode in ['sampled','greedy']),'Test panel incomplete'
    out=dict(source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),maps=data['maps'],placements_per_map=data['placements_per_map'],training_seeds=[0,1,2],uncertainty='Map-cluster bootstrap conditional on these three training seeds; not a confidence interval over new training seeds',modes={})
    maps=data['maps'];rng=np.random.default_rng(72819);indices=rng.integers(maps,size=(10000,maps))
    for mode in ['sampled','greedy']:
        base=r['imitation'][mode];entry={}
        for metric in ['clear','returns']:
            values=np.array([r[name][mode][metric] for name in names]);delta=values.mean(0)-np.array(base[metric]);permap=delta.reshape(-1,maps).mean(0);boot=permap[indices].mean(1)
            entry[metric]=dict(baseline_mean=float(np.mean(base[metric])),candidate_mean=float(values.mean()),candidate_seed_means=values.mean(1).tolist(),paired_mean_difference=float(delta.mean()),map_bootstrap_95ci=np.quantile(boot,[.025,.975]).tolist())
        common=np.array([r[name][mode]['clear'] for name in names]).astype(bool)&np.array(base['clear']).astype(bool)
        turns=np.array([r[name][mode]['turns'] for name in names])-np.array(base['turns'])
        numerator=(turns*common).reshape(3,-1,maps).sum((0,1));denominator=common.reshape(3,-1,maps).sum((0,1))
        boot=numerator[indices].sum(1)/denominator[indices].sum(1)
        entry['common_clear_turn_difference']=dict(mean=float(numerator.sum()/denominator.sum()),map_bootstrap_95ci=np.quantile(boot,[.025,.975]).tolist())
        out['modes'][mode]=entry
    efficiency={};eff_rng=np.random.default_rng(2901);eff_indices=eff_rng.integers(maps,size=(10000,maps))
    for name,results in r.items():
        if name=='imitation':continue
        efficiency[name]={}
        for mode,a in results.items():
            b=r['imitation'][mode];both=(np.array(a['clear'])>0)&(np.array(b['clear'])>0)
            delta=np.array(a['turns'])-np.array(b['turns']);sums=(delta*both).reshape(-1,maps).sum(0);counts=both.reshape(-1,maps).sum(0)
            boot=sums[eff_indices].sum(1)/counts[eff_indices].sum(1)
            efficiency[name][mode]=dict(common_clear_turn_difference=float(sums.sum()/counts.sum()),map_bootstrap_95ci=np.quantile(boot,[.025,.975]).tolist(),common_success_episodes=int(both.sum()))
    out['individual_efficiency']=efficiency
    (ROOT/'results/autoregressive-anchor-efficiency.json').write_text(json.dumps(efficiency,indent=2)+'\n')
    suites=['autoregressive-anchor-screen','autoregressive-anchor-policy1','autoregressive-anchor-policy01-replicates','autoregressive-anchor-navigation']
    jobs=[];pipeline=0
    for name in suites:
        source=json.loads((ROOT/'results'/f'{name}.json').read_text());pipeline+=source['wall_seconds']
        for name,job in source['results'].items():
            last=job['evaluations'][-1];jobs.append(dict(job=name,decisions=last['decisions'],train_seconds=last['train_seconds']))
    out['compute']=dict(jobs=jobs,total_decisions=sum(j['decisions'] for j in jobs),training_seconds=sum(j['train_seconds'] for j in jobs),training_pipeline_wall_seconds=pipeline,test_panel_wall_seconds=data['wall_seconds'])
    (ROOT/'results/autoregressive-anchor-summary.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))
if __name__=='__main__':main()
