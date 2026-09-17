"""Confirm the bounded tactical-retention follow-up on fresh test placements."""
import hashlib,json,pathlib,sys,time
import numpy as np
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/autoregressive-ordinary-v1/scripts'))
from ordinary_eval import SOURCE,evaluate
from tactical_models import Policy

@torch.no_grad()
def main():
    torch.set_num_threads(1);start=time.monotonic()
    selected='wait-seed0'
    suite=ROOT/'learning-runs/autoregressive-ordinary-retain'
    paths={'original_source':SOURCE,'source':ROOT/'learning-runs/autoregressive-survival-balanced/runs/balanced-seed0/latest.pt','control':suite/'runs/control-seed0/latest.pt','selected':suite/'runs'/selected/'latest.pt'}
    rule='Evaluate the single predeclared small-encounter correction candidate at +1M; follow-up motivated by tactical regression. Same held-out test layouts as first confirmation, with fresh placements; no model updates use these results.'
    selection=dict(selected=selected,rule=rule,checkpoints={k:dict(path=str(v),sha256=hashlib.sha256(v.read_bytes()).hexdigest()) for k,v in paths.items()},test_seed=940121,test_maps=100,episodes_per_map=32)
    (suite/'selection.json').write_text(json.dumps(selection,indent=2)+'\n')
    print('Frozen selection',selected,flush=True)
    corpus=json.loads((suite/'manifest.json').read_text())['corpus']
    results={}
    for name,path in paths.items():
        c=torch.load(path,map_location='cpu',weights_only=False)
        assert c['decisions']==({'original_source':35000320,'source':40000512}.get(name,41000960))
        model=Policy('d4_exact',128).cuda().eval();model.load_state_dict(c['model']);results[name]={}
        for mode in ['sampled','greedy']:
            r=evaluate(model,c['job'],corpus,seed=940121,batch=3200,mode=mode,map_limit=100,split='test')
            results[name][mode]=r
            print(name,mode,{k:r[k] for k in ['clear','death','timeout','turns']},flush=True)
        del model,c
    comparisons={};rng=np.random.default_rng(940122)
    for mode in ['sampled','greedy']:
        comparisons[mode]={}
        for other in ['original_source','source','control']:
            a=np.array(results['selected'][mode]['episodes']['clear']);b=np.array(results[other][mode]['episodes']['clear'])
            delta=a-b;per_map=delta.reshape(32,100).mean(0)
            boot=per_map[rng.integers(0,100,size=(20000,100))].mean(1)
            comparisons[mode][other]=dict(delta_pp=100*delta.mean(),map_bootstrap_95_pp=(100*np.quantile(boot,[.025,.975])).tolist(),rescued=int((delta>0).sum()),regressed=int((delta<0).sum()))
    result=dict(selection=selection,results=results,comparisons=comparisons,wall_seconds=time.monotonic()-start,caveat='One training seed; map-cluster intervals describe evaluation uncertainty, not PPO seed variance. Test layouts are held out from training.')
    (ROOT/'results/autoregressive-ordinary-retain-confirmation.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(comparisons,indent=2),flush=True)

if __name__=='__main__':main()
