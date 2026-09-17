"""Compact final comparison, including ordinary-floor retention and residual deaths."""
import hashlib,json,pathlib
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[2]

def read(name):return json.loads((ROOT/'results'/name).read_text())

def main():
    balanced=read('autoregressive-survival-balanced.json')
    first=read('autoregressive-survival-targeted.json')
    source=read('autoregressive-survival.json')['results']['exploration-seed0']['evaluations'][-1]
    control=first['results']['control-seed0']['evaluations'][-1];final=balanced['evaluations'][-1]
    ordinary={};rng=np.random.default_rng(917)
    for mode in ['sampled','greedy']:
        ordinary[mode]=dict(clear_rates={n:r[mode]['clear_rate'] for n,r in [('source',source),('control',control),('balanced',final)]},comparisons={})
        for name,row in [('source',source),('control',control)]:
            keys=sorted(final[mode]['maps']);assert keys==sorted(row[mode]['maps'])
            delta=np.array([final[mode]['maps'][k]['clear_rate']-row[mode]['maps'][k]['clear_rate'] for k in keys])
            boot=delta[rng.integers(0,len(keys),size=(20000,len(keys)))].mean(1)
            ordinary[mode]['comparisons'][name]=dict(delta_pp=100*delta.mean(),map_bootstrap_95_pp=(100*np.quantile(boot,[.025,.975])).tolist())
    panels={}
    for panel in ['original','novel','far']:
        data=read(f'autoregressive-survival-targeted-confirmation-balanced-{panel}.json')
        summaries={name:{k:float(np.mean([r[k] for r in rows])) for k in ['clear','turns','reached_cover','multi_adjacent_turns']} for name,rows in data['results'].items()}
        panels[panel]=dict(episodes_per_policy=2048,base_geometries=8,summaries=summaries,comparisons=data['comparisons'])
        if panel=='original':
            groups=np.arange(512)%64//16
            panels[panel]['families']={name:{f:float(np.array([r['clear'] for r in rows])[:,groups==i].mean()) for i,f in enumerate(['hallway','diagonal_pocket','passing_enemy','separated_groups'])} for name,rows in data['results'].items()}
    deaths=read('autoregressive-survival-balanced-remaining.json')
    checkpoint=ROOT/'learning-runs/autoregressive-survival-balanced/runs/balanced-seed0/latest.pt'
    result=dict(checkpoint=str(checkpoint),checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),cumulative_decisions=final['decisions'],additional_decisions=5000192,training_seconds={**{k:v['additional_train_seconds'] for k,v in first['results'].items()},'balanced-seed0':balanced['additional_train_seconds']},ordinary=ordinary,tactical=panels,original_failure_examples={str(i):bool(deaths['episodes']['policy']['clear'][i]) for i in [24,29]},remaining=deaths['groups'],limitations=['One training seed; adaptive curriculum development.','Original and first novel panels informed development; far panel geometry fixed before the last arm and not used for checkpoint selection.','All tactical scenarios start with remembered local terrain; no claim of general real-Crawl survival competence.','The diagnostic cover controller is privileged and is not an optimality or unavoidability oracle.'])
    (ROOT/'results/autoregressive-survival-balanced-summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(ordinary=ordinary,training_seconds=result['training_seconds'],examples=result['original_failure_examples']),indent=2))

if __name__=='__main__':main()
