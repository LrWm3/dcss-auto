"""Diagnose existing no-travel checkpoints; no training or policy changes."""
import ctypes as C
import json
import pathlib
import subprocess
import sys
import time
import numpy as np
import torch
from torch import nn
from torch.distributions import Categorical
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/vision15-curriculum-v1/scripts'))
from learn_env_ring_multi import Env
from run_ring_ablations import digest, corpus_manifest

class Policy(nn.Module):
 def __init__(self):
  super().__init__();self.body=nn.Sequential(nn.Linear(958,128),nn.Tanh(),nn.Linear(128,128),nn.Tanh());self.actor=nn.Linear(128,9);self.critic=nn.Linear(128,1)
 def forward(self,o,m):return Categorical(logits=self.actor(self.body(o)).masked_fill(m==0,-1e9))

def main():
 torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
 folder=pathlib.Path(__file__).parent;build=folder/'build';build.mkdir(exist_ok=True)
 lib=build/'probe.so'
 flags=['-DFRONTIER_TRAVEL=0','-DOGRE_COUNT=0','-DMONSTER_WAKE_LOS=1','-DTERRAIN_LOS=1','-DGLOBAL_ENEMIES=0','-DLEARN_ENEMIES=40','-DMULTI_MAP','-DSLEEP_ON','-DEXPLORE_REWARD','-DMARK_WALLS','-DEXPLORE_MILLI=2','-DFRONTIER_RING_MEMORY_WALLS_OBS','-DKNOWN_FRONTIER','-DFRONTIER_ROUTE_CUE_OBS','-DFAST_FRONTIER','-DLEARN_BLOCK_SIZE=4','-DDEATH_MILLI=1000','-DCLEAR_PER_ENEMY_MILLI=0']
 subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*flags,str(folder/'probe.cu'),'-o',str(lib)],check=True)
 report={'training_performed':False,'evaluation_seed':900000,'deadline':2048,'episodes_per_policy':1024,'source_hashes':{str(p.relative_to(ROOT)):digest(p) for p in [folder/'run.py',folder/'probe.cu',ROOT/'branches/vision15-curriculum-v1/src/learn.cu',ROOT/'branches/vision15-curriculum-v1/src/sim.h']},'policies':{}}
 reference=json.loads((ROOT/'results/vision15-curriculum-10m.json').read_text())['checkpoints'][-1]
 cases=[('curriculum','vision15-curriculum-stage2-10m','sampled'),('fixed512','vision15-no-travel-early-10m','fixed512'),('fixed2048','vision15-no-travel-train2048-10m','fixed2048')]
 start=time.monotonic()
 for label,suite,key in cases:
  suite=ROOT/'learning-runs'/suite;manifest=json.loads((suite/'manifest.json').read_text());corpus=pathlib.Path(manifest['corpus']);assert corpus_manifest(corpus)==manifest['maps']
  path=suite/'runs/vision15_no_travel-seed0/snapshots/000010027008.pt';saved=torch.load(path,weights_only=False,map_location='cpu');model=Policy().cuda().eval();model.load_state_dict(saved['model'])
  env=Env(1024,24,seed=900000,corpus=corpus/'validation',map_limit=32,map_filter=-2,library_path=lib)
  p=C.c_void_p;i=C.c_int;env.lib.deaths_step.argtypes=[p,i,p,p,p,i,p,p,p,p,p,p];env.lib.deaths_probe.argtypes=[p,i,p,p,p,p,p,p]
  active=torch.ones(1024,dtype=torch.bool,device='cuda');diag=torch.zeros((1024,16),device='cuda');before=torch.empty_like(env.state);oldmask=torch.empty_like(env.mask);probe=torch.full((1024,27),-1.,device='cuda');terminal=torch.zeros_like(env.out)
  # Bounded numeric traces (~130MiB); only aggregate and death summaries persisted.
  trace=np.zeros((2048,1024,16),np.float32);end=np.zeros(1024,np.int32);cf=np.zeros((1024,27),np.float32)-1
  # Verify extension against ordinary step for the first 128 policy steps.
  control=Env(1024,24,seed=900000,corpus=corpus/'validation',map_limit=32,map_filter=-2,library_path=lib)
  torch.manual_seed(900000)
  with torch.no_grad():
   for step in range(2048):
    actions=model(env.obs,env.mask).sample();before.copy_(env.state);oldmask.copy_(env.mask)
    env.check(env.lib.deaths_step(env.state.data_ptr(),1024,C.byref(env.config),C.byref(env.tables),actions.data_ptr(),2048,env.obs.data_ptr(),env.mask.data_ptr(),env.out.data_ptr(),active.data_ptr(),diag.data_ptr(),env.stream))
    if step<128:
     control.step(actions,active=active)
     for a,b in [(env.state,control.state),(env.obs,control.obs),(env.mask,control.mask)]:assert torch.equal(a,b),('parity',label,step)
     assert torch.equal(env.out[active],control.out[active])
    diag[~active]=0;trace[step]=diag.cpu().numpy()
    ended=active & (env.out[:,1]>0);dead=ended & (env.out[:,6]>0)
    if dead.any():
     # Inactive output rows may retain death flags; use a filtered output copy.
     filtered=env.out.clone();filtered[~dead]=0
     env.check(env.lib.deaths_probe(before.data_ptr(),1024,C.byref(env.config),C.byref(env.tables),filtered.data_ptr(),oldmask.data_ptr(),probe.data_ptr(),env.stream))
     assert (probe[dead,:9].gather(1,actions[dead,None])==0).all(), "Fatal action must reproduce death"
     cf[dead.cpu().numpy()]=probe[dead].cpu().numpy()
    terminal[ended]=env.out[ended];end[ended.cpu().numpy()]=step+1;active &= ~ended
   assert not active.any()
  term=terminal.cpu().numpy();deaths=term[:,6]>0
  for k,col in [('clear_rate',2),('death_rate',6),('timeout_rate',7),('kills',3),('turns',5)]:assert float(term[:,col].mean())==reference[key][k],(label,k)
  maximum_hp=env.config[2]
  def group(ids):
   turns=np.arange(2048)[:,None]<end[None,:];turns &= ids[None,:]
   x=trace[turns];damage=x[:,6];total=float(damage.sum())
   return {'episodes':int(ids.sum()),'mean_turns':float(end[ids].mean()),'mean_kills':float(term[ids,3].mean()),'mean_damage_taken':total/int(ids.sum()),'damage_fraction_by_pre_action_adjacent':{str(k):float(damage[x[:,1]==k].sum()/total) for k in range(9)},'multi_adjacent_turn_fraction':float((x[:,1]>=2).mean()),'low_hp_turn_fraction':float((x[:,0]<=maximum_hp*.25).mean()),'low_hp_attacks':int(((x[:,0]<=maximum_hp*.25)&(x[:,8]==2)).sum()),'low_hp_attacks_with_less_adjacent_move':int(((x[:,0]<=maximum_hp*.25)&(x[:,8]==2)&(x[:,10]>0)).sum()),'low_hp_moves_increasing_adjacency':int(((x[:,0]<=maximum_hp*.25)&(x[:,11]>0)).sum())}
  records=[]
  for episode in np.where(deaths)[0]:
   n=end[episode];x=trace[:n,episode];last=x[-1];recent=x[max(0,n-20):];low=np.where(x[:,0]<=maximum_hp*.25)[0]
   records.append({'episode':int(episode),'map_seed':env.metadata[episode%32]['seed'],'turn':int(n),'kills':float(term[episode,3]),'hp_before_fatal':float(last[0]),'adjacent_before_fatal':int(last[1]),'near_awake_before_fatal':int(last[2]),'fatal_action':int(last[8]),'last20_damage':float(recent[:,6].sum()),'last20_max_adjacent':int(recent[:,1].max()),'total_damage':float(x[:,6].sum()),'turns_since_first_quarter_hp':int(n-low[0]) if len(low) else 0,'last20_low_hp_attacks_with_less_adjacent_move':int(((recent[:,0]<=maximum_hp*.25)&(recent[:,8]==2)&(recent[:,10]>0)).sum()),'one_step_surviving_actions':np.where(cf[episode,:9]==1)[0].tolist(),'one_step_surviving_moves':np.where((cf[episode,:9]==1)&(cf[episode,9:18]==1))[0].tolist(),'one_step_surviving_less_adjacent_moves':np.where((cf[episode,:9]==1)&(cf[episode,18:27]==1))[0].tolist()})
  result={'checkpoint_sha256':digest(path),'full_hp':maximum_hp,'regen_per_turn':env.config[7]/100,'clear_rate':float(term[:,2].mean()),'death_rate':float(term[:,6].mean()),'timeout_rate':float(term[:,7].mean()),'all':group(np.ones(1024,bool)),'deaths':group(deaths),'clears':group(term[:,2]>0),'death_records':records,'parity_steps':128,'baseline_metrics_exact':True}
  report['policies'][label]=result;report['elapsed_seconds']=time.monotonic()-start
  (ROOT/'results/vision15-death-diagnostics.json').write_text(json.dumps(report,indent=2)+'\n')
  print(label,json.dumps({k:v for k,v in result.items() if k not in ['death_records','all','clears']}),flush=True)
if __name__=='__main__':main()
