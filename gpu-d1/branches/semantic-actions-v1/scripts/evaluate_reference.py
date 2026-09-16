"""Deterministic baseline using exactly the learned five-action interface."""
import hashlib,json,pathlib,time
import torch
from assets import ROOT,ASSETS
from run_experiment import plan
from learn_env_ring_multi import Env

@torch.no_grad()
def main():
 torch.set_num_threads(1);m=plan();j=m['jobs'][0];lib=pathlib.Path(j['eval_library']);assert hashlib.sha256(lib.read_bytes()).hexdigest()==lib.with_suffix('.sha256').read_text().strip()
 env=Env(1024,24,seed=900000,corpus=pathlib.Path(m['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=lib,limit=2048)
 active=torch.ones(1024,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(env.out);counts=torch.zeros(1024,5,device='cuda');turns=torch.zeros(1024,device='cuda');returns=torch.zeros_like(turns);start=time.monotonic()
 for step in range(2048):
  if not active.any():break
  a=env.heuristic().clone();assert bool(((env.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all())
  counts.scatter_add_(1,a[:,None],active.float()[:,None]);env.step(a,active=active);turns+=active*env.out[:,26];returns+=active*env.out[:,0]
  ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended];active&=~ended
 assert not active.any();assert torch.equal(turns,terminal[:,5]);assert bool((turns<=2048).all())
 clear=terminal[:,2]>0
 r=dict(episodes=1024,seed=900000,library_sha256=hashlib.sha256(lib.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),rules='Attack if adjacent; else rest if available; else wait if awake visible; else engage if available; else explore if available; else wait.',metrics=dict(clears=int(clear.sum()),deaths=int(terminal[:,6].sum()),timeouts=int(terminal[:,7].sum()),clear_rate=float(clear.float().mean()),kills=float(terminal[:,3].mean()),physical_turns=float(turns.mean()),clear_only_turns=float(turns[clear].mean()),policy_decisions=float(counts.sum(1).mean()),shaped_return=float(returns.mean()),actions={name:float(counts[:,k].mean()) for k,name in enumerate(['attack','explore','engage','wait','rest'])},evaluation_seconds=time.monotonic()-start),episodes_detail=[dict(map_seed=env.metadata[i%32]['seed'],clear=bool(clear[i]),death=bool(terminal[i,6]),timeout=bool(terminal[i,7]),kills=int(terminal[i,3]),physical_turns=int(turns[i])) for i in range(1024)])
 (ROOT/'results/semantic-actions-reference.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r['metrics']),flush=True)
if __name__=='__main__':main()
