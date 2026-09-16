"""Validate scenario mechanics, mixed-world reset/resume, and one PPO update per arm."""
import json,pathlib,subprocess,sys
import torch
from assets import ASSETS,ROOT
from tactical_env import TacticalEnv,MixedEnv
from learn_env_ring_multi import Env
from prepare import plan,initialize
import run_ring_ablations as runner

def main():
 torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
 manifest=plan();job=manifest['jobs'][0];corpus=pathlib.Path(manifest['corpus']);checks={}
 for task in ['target','sleep']:
  base=Env(64,24,seed=17,corpus=corpus/'train',map_limit=2,library_path=job['train_library'])
  tactical=TacticalEnv(64,24,seed=71,corpus=ASSETS/task/'train',map_limit=16,map_filter=-2,library_path=ASSETS/'tactical.so')
  _,stats=tactical.probe(0);assert torch.all(stats[:,11]==1)
  if task=='sleep':
   assert torch.all(stats[:,4]==0) and torch.all(stats[:,7]==7)
   initial=tactical.obs[:,650].clone()
   for _ in range(80):tactical.step(torch.full((64,),8,device='cuda',dtype=torch.long))
   _,stats=tactical.probe(0)
   assert torch.all(stats[:,4]==0) and torch.all(stats[:,0]==18) and torch.all(stats[:,7]==7)
   assert torch.all(tactical.obs[:,650]>=initial)
   tactical.reset(71)
  mixed=MixedEnv(base,tactical,19)
  # Start some scenarios now to exercise episode switches and paused ordinary worlds.
  mixed.is_tactical[::2]=True;mixed.refresh();torch.manual_seed(17)
  for step in range(128):
   before=mixed.is_tactical.clone();action=torch.distributions.Categorical(probs=mixed.mask).sample()
   if step==64:
    state=mixed.state.clone();snap=mixed.snapshot();mixed.step(action)
    expected=[mixed.state.clone(),mixed.obs.clone(),mixed.mask.clone(),mixed.out.clone(),mixed.counts.clone(),mixed.is_tactical.clone()]
    mixed.state.copy_(state);mixed.restore(snap);mixed.step(action)
    assert all(torch.equal(a,b) for a,b in zip(expected,[mixed.state,mixed.obs,mixed.mask,mixed.out,mixed.counts,mixed.is_tactical]))
   else:mixed.step(action)
   live=mixed.out[:,1]==0;assert torch.equal(before[live],mixed.is_tactical[live])
  checks[task]=dict(mixed_resume_exact=True,counts=mixed.counts.cpu().tolist())
 smoke=ROOT/'learning-runs/choice-practice-smoke-v2';smoke.mkdir(parents=True,exist_ok=True);store=runner.Store(smoke,3*runner.GIB,10*runner.GIB)
 jobs=[dict(j,steps=30015488+32768,validation_maps=2,eval_per_map=2) for j in manifest['jobs'][:3]]
 manifest['jobs']=jobs;store.json('manifest.json',manifest)
 for j in jobs:
  initialize(store,j)
  for _ in range(2):subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',j['id'],'--output',str(smoke),'--max-disk-gb','3','--min-free-gb','10'],check=True)
 checks['ppo_and_resume_all_arms']=True
 (ROOT/'results/choice-practice-preflight.json').write_text(json.dumps(checks,indent=2)+'\n');print('Choice-practice preflight passed',flush=True)
if __name__=='__main__':main()
