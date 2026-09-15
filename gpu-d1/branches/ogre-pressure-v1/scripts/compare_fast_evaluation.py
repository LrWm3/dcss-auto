"""Compare all terminal counters and returns on the fixed 1024-episode panel."""
import json,pathlib,sys,time,torch
from torch.distributions import Distribution
from benchmark_pipeline import Policy
from learn_env_ring_multi import Env
from learn_env import ROOT
root=ROOT.parents[1];torch.set_num_threads(1);Distribution.set_default_validate_args(False)
saved=torch.load(root/'learning-runs/ogre2-baseline-150m/runs/ogre2_base-seed0/latest.pt',map_location='cpu',weights_only=False)
reference=None;results=[]
with torch.no_grad():
 for lib,fast in [(sys.argv[1],False),(sys.argv[2],True)]:
  ev=Env(1024,26,corpus=root/'fixtures/d1-corpus-388/validation',map_limit=32,map_filter=-2,library_path=pathlib.Path(lib))
  model=Policy(ev.obs.shape[1],ev.mask.shape[1]).cuda();model.load_state_dict(saved['model'])
  ev.reset(900000);torch.manual_seed(900000)
  active=torch.ones(1024,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(ev.out)
  returns=torch.zeros(1024,device='cuda');exposure=torch.zeros((1024,3),device='cuda')
  torch.cuda.synchronize();start=time.perf_counter()
  for _ in range(1024):
   dist,_=model(ev.obs,ev.mask);_,out=ev.step(dist.sample(),active=active if fast else None)
   returns+=active*out[:,0];exposure+=active[:,None]*out[:,15:18]
   ended=active & (out[:,1]>0);terminal[ended]=out[ended];terminal[ended,15:18]=exposure[ended];active &= ~ended
  torch.cuda.synchronize();elapsed=time.perf_counter()-start
  assert not active.any().item()
  outcome=(terminal.cpu(),returns.cpu())
  if reference is None:reference=outcome
  else:
   assert all(torch.equal(a,b) for a,b in zip(reference,outcome)), 'evaluation counters or returns changed'
  results.append(dict(fast=fast,seconds=elapsed,decisions=saved['decisions'],terminal_means=outcome[0].mean(0).tolist()))
  del ev,model
print(json.dumps(results,indent=2));print('PASS: all episode counters and returns match, including wake/adjacency/near diagnostics')
