"""Matched 10M semantic-policy evaluation with an observation-only REST override."""
import json,pathlib,sys,time,hashlib
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/semantic-actions-v1/scripts'))
import torch
from tactical_models import Policy
from learn_env_ring_multi import Env

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

@torch.no_grad()
def main():
 torch.set_num_threads(1)
 suite=ROOT/'learning-runs/semantic-actions'
 manifest=json.loads((suite/'manifest.json').read_text());j=manifest['jobs'][0]
 checkpoint=suite/'runs/semantic-seed0/latest.pt';saved=torch.load(checkpoint,map_location='cpu',weights_only=False)
 model=Policy(j['architecture'],j['width']).cuda();model.load_state_dict(saved['model']);model.eval()
 lib=pathlib.Path(j['eval_library']);assert digest(lib)==lib.with_suffix('.sha256').read_text().strip()
 env=Env(1024,24,seed=900000,corpus=pathlib.Path(manifest['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=lib,limit=2048)
 historical=json.loads((ROOT/'results/semantic-actions-training.json').read_text())['final']
 results={}
 for mode in ['sampled','greedy']:
  for override in [False,True]:
   key=mode+('_rest' if override else '_baseline');env.reset(900000);torch.manual_seed(900000)
   active=torch.ones(1024,device='cuda',dtype=torch.bool);terminal=torch.zeros_like(env.out)
   counts=torch.zeros(1024,5,device='cuda');turns=torch.zeros(1024,device='cuda');rewards=torch.zeros_like(turns);forced=torch.zeros_like(turns);rest_turns=torch.zeros_like(turns);start=time.monotonic()
   for _ in range(2048):
    if not active.any():break
    dist,_=model(env.obs,env.mask);a=dist.sample() if mode=='sampled' else dist.probs.argmax(-1)
    if override:
     change=active&(env.mask[:,4]>0)&(a!=4);forced+=change
     a=torch.where(env.mask[:,4]>0,4,a)
    assert bool(((env.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all())
    counts.scatter_add_(1,a[:,None],active.float()[:,None]);env.step(a,active=active)
    turns+=active*env.out[:,26];rewards+=active*env.out[:,0];rest_turns+=active*env.out[:,35]
    ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended];active&=~ended
   assert not active.any();assert torch.equal(turns,terminal[:,5]);assert bool((turns<=2048).all())
   t=terminal.cpu();metrics=dict(clears=int(t[:,2].sum()),deaths=int(t[:,6].sum()),timeouts=int(t[:,7].sum()),kills=float(t[:,3].mean()),physical_turns=float(turns.mean()),policy_decisions=float(counts.sum(1).mean()),shaped_return=float(rewards.mean()),forced_rests=float(forced.mean()),rest_turns=float(rest_turns.mean()),actions={name:float(counts[:,k].mean()) for k,name in enumerate(['attack','explore','engage','wait','rest'])},evaluation_seconds=time.monotonic()-start)
   if not override:
    for target,source in [('clears','clear_rate'),('deaths','death_rate'),('timeouts','timeout_rate')]:assert metrics[target]==round(historical[mode][source]*1024),(key,target)
   results[key]=dict(metrics=metrics,episodes=[dict(clear=bool(row[2]),death=bool(row[6]),timeout=bool(row[7]),kills=int(row[3]),turns=int(row[5])) for row in t])
   print(key,json.dumps(metrics),flush=True)
 paired={}
 for mode in ['sampled','greedy']:
  a=results[mode+'_baseline']['episodes'];b=results[mode+'_rest']['episodes']
  paired[mode]=dict(gained_clears=sum(not x['clear'] and y['clear'] for x,y in zip(a,b)),lost_clears=sum(x['clear'] and not y['clear'] for x,y in zip(a,b)))
 result=dict(checkpoint_sha256=digest(checkpoint),library_sha256=digest(lib),script_sha256=digest(pathlib.Path(__file__)),decisions=saved['decisions'],episodes=1024,evaluation_seed=900000,intervention='Force action REST whenever its existing observation-only availability mask permits it; otherwise preserve model action. No retraining.',results=results,paired=paired)
 (ROOT/'results/semantic-actions-rest-override.json').write_text(json.dumps(result,indent=2)+'\n');print('Paired',paired,flush=True)
if __name__=='__main__':main()
