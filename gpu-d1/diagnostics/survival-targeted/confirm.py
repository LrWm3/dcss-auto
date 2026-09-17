"""Fresh encounter seeds on the predeclared novel geometries, after training."""
import argparse,json,pathlib,sys,time
import numpy as np
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/autoregressive-survival-targeted-v2/scripts'))
from tactical_env import TacticalEnv
from tactical_models import Policy

@torch.no_grad()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--balanced',action='store_true');ap.add_argument('--panel',choices=['novel','far','original'],default='novel');args=ap.parse_args()
    torch.set_num_threads(1);start=time.monotonic()
    paths={
      'source':ROOT/'learning-runs/autoregressive-survival/runs/exploration-seed0/latest.pt',
      'control':ROOT/'learning-runs/autoregressive-survival-targeted/runs/control-seed0/latest.pt',
      'targeted':ROOT/'learning-runs/autoregressive-survival-targeted/runs/targeted-seed0/latest.pt'}
    if args.balanced:paths['balanced']=ROOT/'learning-runs/autoregressive-survival-balanced/runs/balanced-seed0/latest.pt'
    corpora={'novel':'autoregressive-survival-targeted-assets','far':'autoregressive-survival-balanced-assets','original':'autoregressive-survival-assets'}
    corpus=ROOT/'learning-runs'/corpora[args.panel]/'heldout'
    env=TacticalEnv(512,24,seed=831001,corpus=corpus,map_limit=64,map_filter=-2,library_path=str(ROOT/'learning-runs/autoregressive-survival-assets/survival.so'))
    results={}
    for name in [*paths,'cover']:
        if name!='cover':
            saved=torch.load(paths[name],map_location='cpu',weights_only=False)
            if name!='source':assert saved['decisions']==40000512
            model=Policy('d4_exact',128).cuda().eval();model.load_state_dict(saved['model']);del saved
        results[name]=[]
        for seed in [831001,832001,833001,834001]:
            env.reset(seed);active=torch.ones(512,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(env.out)
            reached=torch.zeros_like(active);exposure=torch.zeros(512,device='cuda')
            for step in range(2048):
                script,stats=env.probe(1);reached|=active&stats[:,5].bool();exposure+=active&(stats[:,2]>1)
                actions=script.clone() if name=='cover' else model(env.obs,env.mask)[0].greedy()
                assert ((env.mask.gather(1,actions[:,None]).squeeze(1)>0)|~active).all()
                env.step(actions,active=active);done=active&(env.out[:,1]>0);terminal[done]=env.out[done];active&=~done
                if not active.any():break
            assert not active.any()
            results[name].append(dict(seed=seed,clear=terminal[:,2].cpu().tolist(),turns=terminal[:,5].cpu().tolist(),reached_cover=reached.cpu().tolist(),multi_adjacent_turns=exposure.cpu().tolist()))
        print(name,'clear',np.mean([r['clear'] for r in results[name]]),flush=True)
    rng=np.random.default_rng(619);comparisons={}
    candidate='balanced' if args.balanced else 'targeted'
    for other in [x for x in results if x!=candidate]:
        delta=np.array([r['clear'] for r in results[candidate]])-np.array([r['clear'] for r in results[other]])
        # Resample base geometry, preserving all rotations and placement seeds.
        groups=np.arange(512)%64//8
        per_geometry=np.array([delta[:,groups==i].mean() for i in range(8)])
        boot=per_geometry[rng.integers(0,8,size=(20000,8))].mean(1)
        comparisons[other]=dict(delta_pp=100*delta.mean(),geometry_bootstrap_95_pp=(100*np.quantile(boot,[.025,.975])).tolist(),per_geometry_delta_pp=(100*per_geometry).tolist())
    output=dict(checkpoints={k:str(v) for k,v in paths.items()},corpus=str(corpus),candidate=candidate,seeds=[831001,832001,833001,834001],mode='greedy',results=results,comparisons=comparisons,wall_seconds=time.monotonic()-start)
    suffix=('-balanced-'+args.panel) if args.balanced else ('' if args.panel=='novel' else '-'+args.panel)
    (ROOT/'results'/f'autoregressive-survival-targeted-confirmation{suffix}.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    print(json.dumps(comparisons,indent=2),flush=True)

if __name__=='__main__':main()
