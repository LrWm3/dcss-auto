"""Report paired differences without treating rotations as independent layouts."""
import json,pathlib
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[2]

def main():
    raw=json.loads((ROOT/'results/autoregressive-survival-targeted.json').read_text())
    initial=json.loads((ROOT/'results/autoregressive-survival-targeted-initial.json').read_text())
    old=json.loads((ROOT/'results/autoregressive-survival.json').read_text())['results']['exploration-seed0']['evaluations'][-1]
    final={k:v['evaluations'][-1] for k,v in raw['results'].items()};assert len(final)==2
    rng=np.random.default_rng(1729);comparisons={}
    for panel in ['tactics','target_tactics']:
        comparisons[panel]={}
        for mode in ['sampled','greedy']:
            target=np.array(final['targeted-seed0'][panel][mode]['episodes']['clear'])
            sources={'control':final['control-seed0'][panel][mode],
                     'source':old['tactics'][mode] if panel=='tactics' else initial['policy'][mode]}
            comparisons[panel][mode]={}
            for label,source in sources.items():
                delta=target-np.array(source['episodes']['clear']);groups=np.arange(512)%64//8
                per_geometry=np.array([delta[groups==i].mean() for i in range(8)])
                boot=per_geometry[rng.integers(0,8,size=(20000,8))].mean(1)
                comparisons[panel][mode][label]=dict(delta_pp=100*delta.mean(),geometry_bootstrap_95_pp=(100*np.quantile(boot,[.025,.975])).tolist(),per_geometry_delta_pp=(100*per_geometry).tolist(),rescued=int((delta==1).sum()),regressed=int((delta==-1).sum()))
    result=dict(comparisons=comparisons,additional_train_seconds={k:v['additional_train_seconds'] for k,v in raw['results'].items()},caveat='One training seed; eight base-geometry clusters per tactical panel. Original panel informed the curriculum design.')
    (ROOT/'results/autoregressive-survival-targeted-comparison.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
