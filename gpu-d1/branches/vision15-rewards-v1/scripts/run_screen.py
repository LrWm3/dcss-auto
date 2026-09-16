"""Two 10M reward variants against the retained fixed-2048 baseline."""
import ctypes as C
import json
import pathlib
import subprocess
import sys
import time
import torch
from torch import nn
from torch.distributions import Categorical
from run_ring_ablations import ROOT, digest, library_key
from learn_env_ring_multi import Env

class Policy(nn.Module):
 def __init__(self):
  super().__init__();self.body=nn.Sequential(nn.Linear(958,128),nn.Tanh(),nn.Linear(128,128),nn.Tanh());self.actor=nn.Linear(128,9);self.critic=nn.Linear(128,1)
 def forward(self,o,m):return Categorical(logits=self.actor(self.body(o)).masked_fill(m==0,-1e9))

def main():
 root=ROOT.parents[1];suite=root/'learning-runs/vision15-rewards-10m'
 start=time.monotonic()
 subprocess.run([sys.executable,str(ROOT/'scripts/run_ring_ablations.py'),'--output',str(suite),'--steps','10000000','--seeds','0','--variants','death4,completion'],check=True)
 manifest=json.loads((suite/'manifest.json').read_text());baseline=root/'learning-runs/vision15-no-travel-train2048-10m';base_manifest=json.loads((baseline/'manifest.json').read_text());assert manifest['maps']==base_manifest['maps']
 base_job=base_manifest['jobs'][0];base_lib=next((baseline/'build').glob('*.so'))
 baseline_result=root/'results/vision15-no-travel-train2048-10m.json'
 original=json.loads(baseline_result.read_text());corpus=pathlib.Path(manifest['corpus'])
 saved=torch.load(baseline/'runs/vision15_no_travel-seed0/snapshots/000010027008.pt',weights_only=False,map_location='cpu');model=Policy().cuda().eval();model.load_state_dict(saved['model']);torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
 report=dict(seed=0,training_deadline=2048,evaluation_deadline=2048,baseline_sha256=digest(baseline_result),manifest=manifest,script_sha256=digest(pathlib.Path(__file__)),policies={'baseline':original['checkpoints']},validation={})
 for job in manifest['jobs']:
  ignored={'name','id','death_milli','kill_milli','clear_milli'}
  assert {k:v for k,v in job.items() if k not in ignored}=={k:v for k,v in base_job.items() if k not in ignored}
  lib=suite/'build'/(library_key(job)+'.so')
  a=Env(64,24,seed=900000,corpus=corpus/'validation',map_limit=32,map_filter=-2,library_path=base_lib)
  b=Env(64,24,seed=900000,corpus=corpus/'validation',map_limit=32,map_filter=-2,library_path=lib)
  active=torch.ones(64,dtype=torch.bool,device='cuda');previous=torch.zeros(64,device='cuda');counts=torch.zeros(3,device='cuda');torch.manual_seed(900000)
  with torch.no_grad():
   for step in range(2048):
    assert torch.equal(a.obs,b.obs) and torch.equal(a.mask,b.mask)
    action=model(a.obs,a.mask).sample();a.step(action,active=active);b.step(action,active=active)
    assert torch.equal(a.state,b.state) and torch.equal(a.out[active,1:],b.out[active,1:])
    kills=a.out[:,3]-previous
    expected=a.out[:,0]+kills*(job['kill_milli']/1000-1)+a.out[:,2]*(job['clear_milli']/1000-3)-a.out[:,6]*(job['death_milli']/1000-1)
    assert torch.allclose(b.out[active,0],expected[active],atol=4e-6,rtol=0),(job['name'],step)
    counts+=torch.stack((kills[active].sum(),a.out[active,2].sum(),a.out[active,6].sum()))
    previous=a.out[:,3].clone();active &= a.out[:,1]==0
   assert not active.any();assert (counts>0).all()
  report['validation'][job['name']]=dict(full_state_observation_mask_nonreward_outputs_equal=True,reward_formula_passed=True,kills=int(counts[0]),clears=int(counts[1]),deaths=int(counts[2]),episodes=64)
  curve=json.loads((suite/'runs'/job['id']/'curve.json').read_text());assert [r['decisions'] for r in curve]==[r['decisions'] for r in original['checkpoints']]
  for row in curve:row['checkpoint_sha256']=digest(suite/'runs'/job['id']/'snapshots'/f"{row['decisions']:012d}.pt")
  # All variants must start from the same untrained policy behavior.
  for key in ['clear_rate','death_rate','timeout_rate','kills','turns']:assert curve[0]['sampled'][key]==original['checkpoints'][0]['sampled'][key]
  report['policies'][job['name']]=curve
  print('Validation passed:',job['name'],report['validation'][job['name']],flush=True)
 report['wall_seconds']=time.monotonic()-start
 (root/'results/vision15-rewards-10m.json').write_text(json.dumps(report,indent=2)+'\n')
 for label,curve in report['policies'].items():print(label,json.dumps({k:curve[-1]['sampled'][k] for k in ['clear_rate','death_rate','timeout_rate','turns','kills']}),flush=True)
if __name__=='__main__':main()
