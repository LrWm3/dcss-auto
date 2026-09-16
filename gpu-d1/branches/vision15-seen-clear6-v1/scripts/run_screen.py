"""Compare +6 against +3 clear reward with discovered-floor input."""
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
  super().__init__();self.body=nn.Sequential(nn.Linear(959,128),nn.Tanh(),nn.Linear(128,128),nn.Tanh());self.actor=nn.Linear(128,9);self.critic=nn.Linear(128,1)
 def forward(self,o,m):return Categorical(logits=self.actor(self.body(o)).masked_fill(m==0,-1e9))

def main():
 root=ROOT.parents[1];suite=root/'learning-runs/vision15-seen-clear6-10m'
 start=time.monotonic()
 subprocess.run([sys.executable,str(ROOT/'scripts/run_ring_ablations.py'),'--output',str(suite),'--steps','10000000','--seeds','0','--variants','tiles_seen_clear6'],check=True)
 manifest=json.loads((suite/'manifest.json').read_text());baseline=root/'learning-runs/vision15-progress-10m';base_manifest=json.loads((baseline/'manifest.json').read_text());assert manifest['maps']==base_manifest['maps']
 base_job=next(j for j in base_manifest['jobs'] if j['name']=='tiles_seen');base_lib=baseline/'build'/(library_key(base_job)+'.so')
 baseline_result=root/'results/vision15-progress-10m.json'
 original={'checkpoints':json.loads(baseline_result.read_text())['policies']['tiles_seen']};corpus=pathlib.Path(manifest['corpus'])
 saved=torch.load(baseline/'runs/tiles_seen-seed0/snapshots/000010027008.pt',weights_only=False,map_location='cpu');model=Policy().cuda().eval();model.load_state_dict(saved['model']);torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
 report=dict(seed=0,training_deadline=2048,evaluation_deadline=2048,baseline_sha256=digest(baseline_result),manifest=manifest,script_sha256=digest(pathlib.Path(__file__)),policies={'tiles_seen_clear3':original['checkpoints']},validation={})
 for job in manifest['jobs']:
  ignored={'name','id','clear_milli'}
  assert {k:v for k,v in job.items() if k not in ignored}=={k:v for k,v in base_job.items() if k not in ignored}
  assert (job['kill_milli'],job['clear_milli'],job['death_milli'])==(1000,6000,1000)
  lib=suite/'build'/(library_key(job)+'.so')
  a=Env(64,24,seed=900000,corpus=corpus/'validation',map_limit=32,map_filter=-2,library_path=base_lib)
  b=Env(64,24,seed=900000,corpus=corpus/'validation',map_limit=32,map_filter=-2,library_path=lib)
  cpu=Env(1,24,seed=900000,device='cpu',corpus=corpus/'validation',map_limit=1,map_filter=0,library_path=lib)
  b.lib.learn_progress_test.argtypes=[C.c_void_p,C.c_void_p]
  assert b.lib.learn_progress_test(C.byref(cpu.config),C.byref(cpu.tables))==0
  del cpu
  b.lib.learn_progress_counts.argtypes=[C.c_void_p,C.c_int,C.c_void_p,C.c_void_p]
  raw_counts=torch.empty((64,2),dtype=torch.int32,device='cuda')
  active=torch.ones(64,dtype=torch.bool,device='cuda');previous=torch.zeros(64,device='cuda');counts=torch.zeros(3,device='cuda');torch.manual_seed(900000)
  max_scalar_error=0.
  with torch.no_grad():
   for step in range(2048):
    assert torch.equal(a.obs,b.obs) and torch.equal(a.mask,b.mask)
    b.check(b.lib.learn_progress_counts(b.state.data_ptr(),64,raw_counts.data_ptr(),b.stream))
    expected=raw_counts[:,0].float()/24 if job['progress_input']==1 else raw_counts[:,1].float()/1024
    # CUDA and Torch may implement division by 24 with different rounding.
    # Validate the represented integer exactly and allow <=1 float32 ULP.
    scale=24 if job['progress_input']==1 else 1024
    column=0 if job['progress_input']==1 else 1
    assert torch.equal(torch.round(b.obs[:,958]*scale).int(),raw_counts[:,column])
    error=(b.obs[:,958]-expected).abs().max().item()
    max_scalar_error=max(max_scalar_error,error)
    assert error<=1e-7,(job['name'],step,error)
    action=model(a.obs,a.mask).sample();a.step(action,active=active);b.step(action,active=active)
    assert torch.equal(a.state,b.state) and torch.equal(a.out[active,1:],b.out[active,1:])
    assert torch.allclose(b.out[active,0],a.out[active,0]+3*a.out[active,2],atol=2e-6,rtol=0)
    kills=a.out[:,3]-previous
    counts+=torch.stack((kills[active].sum(),a.out[active,2].sum(),a.out[active,6].sum()))
    previous=a.out[:,3].clone();active &= a.out[:,1]==0
   assert not active.any();assert (counts>0).all()
  report['validation'][job['name']]=dict(full_state_all_observation_mask_nonreward_outputs_equal=True,reward_delta_equals_three_per_clear=True,progress_values_checked_against_state_arrays=True,synthetic_counter_tests=True,encoded_integer_count_exact=True,max_scalar_reference_difference=max_scalar_error,kills=int(counts[0]),clears=int(counts[1]),deaths=int(counts[2]),episodes=64)
  curve=json.loads((suite/'runs'/job['id']/'curve.json').read_text());assert [r['decisions'] for r in curve]==[r['decisions'] for r in original['checkpoints']]
  for row in curve:row['checkpoint_sha256']=digest(suite/'runs'/job['id']/'snapshots'/f"{row['decisions']:012d}.pt")
  init=torch.load(suite/'runs'/job['id']/'snapshots/000000000000.pt',weights_only=False,map_location='cpu')['model']
  base_init=torch.load(baseline/'runs/tiles_seen-seed0/snapshots/000000000000.pt',weights_only=False,map_location='cpu')['model']
  for name,value in base_init.items():assert torch.equal(init[name],value)
  # All variants must start from the same untrained policy behavior.
  for key in ['clear_rate','death_rate','timeout_rate','kills','turns']:assert curve[0]['sampled'][key]==original['checkpoints'][0]['sampled'][key]
  report['policies'][job['name']]=curve
  print('Validation passed:',job['name'],report['validation'][job['name']],flush=True)
 report['wall_seconds']=time.monotonic()-start
 (root/'results/vision15-seen-clear6-10m.json').write_text(json.dumps(report,separators=(',',':'))+'\n')
 for label,curve in report['policies'].items():print(label,json.dumps({k:curve[-1]['sampled'][k] for k in ['clear_rate','death_rate','timeout_rate','turns','kills']}),flush=True)
if __name__=='__main__':main()
