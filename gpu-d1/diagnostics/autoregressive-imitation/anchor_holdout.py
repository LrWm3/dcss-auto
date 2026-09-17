"""Compare selected checkpoints on test layouts; retain paired episode outcomes."""
import argparse,json,pathlib,time
import numpy as np
import torch
import episode_credit as ec
from tactical_models import Policy
from learn_env_ring_multi import Env
ROOT=ec.ROOT

@torch.no_grad()
def evaluate(cp,job,corpus,seed,mode,batch,maps):
    torch.manual_seed(seed)
    model=Policy('d4_exact',128).cuda()
    model.load_state_dict(torch.load(cp,map_location='cpu',weights_only=False)['model'])
    model.eval();torch.manual_seed(seed)
    env=Env(batch,24,seed=seed,corpus=corpus,map_limit=maps,map_filter=-2,library_path=job['eval_library'],limit=2048)
    active=torch.ones(batch,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(env.out)
    moves=torch.zeros(batch,device='cuda');reversals=moves.clone();prev=torch.full((batch,2),-999.,device='cuda')
    for _ in range(2048):
        if not active.any():break
        xy=env.obs[:,652:654].clone();dist,_=model(env.obs,env.mask)
        a=dist.sample() if mode=='sampled' else dist.greedy()
        assert bool(((env.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all())
        env.step(a,active=active);ended=active&(env.out[:,1]>0)
        moving=active&(a<8);moves+=moving
        reversals+=moving&~ended&(env.obs[:,652:654]==prev).all(1)&(xy!=prev).any(1)
        prev=xy;terminal[ended]=env.out[ended];active&=~ended
    assert not active.any()
    t=terminal.cpu().numpy();clear=t[:,2];turn=t[:,5];ret=clear-1e-5*turn
    return dict(clear=clear.tolist(),death=t[:,6].tolist(),timeout=t[:,7].tolist(),turns=turn.tolist(),returns=ret.tolist(),maps=[m['seed'] for m in env.metadata],summary=dict(clear_rate=float(clear.mean()),death_rate=float(t[:,6].mean()),timeout_rate=float(t[:,7].mean()),clear_turns=float(turn[clear>0].mean()) if clear.any() else None,return_mean=float(ret.mean()),reversal_fraction=float(reversals.sum()/moves.sum())))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--suite',default='autoregressive-anchor-screen');ap.add_argument('--jobs',required=True);ap.add_argument('--stage',type=int,default=10000384);ap.add_argument('--output',default='autoregressive-anchor-holdout');ap.add_argument('--maps',type=int,default=100);ap.add_argument('--per-map',type=int,default=16);args=ap.parse_args()
    torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
    suite=ROOT/'learning-runs'/args.suite;m=json.loads((suite/'manifest.json').read_text());jobs=[next(j for j in m['jobs'] if j['id']==s) for s in args.jobs.split(',')]
    corpus=pathlib.Path(m['corpus'])/'test';assert len(list(corpus.glob('*.bin')))>=args.maps
    variants=[('imitation',pathlib.Path(jobs[0]['initial_model']),jobs[0])]+[(j['id'],suite/'runs'/j['id']/'snapshots'/f'{args.stage:012d}.pt',j) for j in jobs]
    results={};start=time.monotonic()
    for name,cp,j in variants:
        results[name]={}
        for mode in ['sampled','greedy']:
            r=evaluate(cp,j,corpus,1930017,mode,args.maps*args.per_map,args.maps);results[name][mode]=r
            if name!='imitation':
                base=results['imitation'][mode];rng=np.random.default_rng(713)
                comparison={}
                for metric in ['clear','returns']:
                    delta=np.array(r[metric])-np.array(base[metric]);permap=delta.reshape(-1,args.maps).mean(0)
                    boot=permap[rng.integers(args.maps,size=(10000,args.maps))].mean(1)
                    comparison[metric]=dict(mean_difference=float(delta.mean()),map_bootstrap_95ci=np.quantile(boot,[.025,.975]).tolist())
                both=(np.array(r['clear'])>0)&(np.array(base['clear'])>0)
                comparison['common_clear_turn_difference']=float((np.array(r['turns'])-np.array(base['turns']))[both].mean()) if both.any() else None
                r['paired_comparison']=comparison
            print(name,mode,r['summary'],r.get('paired_comparison',{}),flush=True)
            (ROOT/'results'/f'{args.output}.json').write_text(json.dumps(dict(results=results,wall_seconds=time.monotonic()-start,seed=1930017,split='test',maps=args.maps,placements_per_map=args.per_map),indent=2)+'\n')
if __name__=='__main__':main()
