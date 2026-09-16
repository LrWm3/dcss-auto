"""Freeze behavior, record per-turn rewards, and rescore discount factors exactly."""
import sys,pathlib,json,subprocess,hashlib,ctypes,time
import numpy as np
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/semantic-actions-v1/scripts'))
from assets import FLAGS
from tactical_models import Policy
from learn_env_ring_multi import Env

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
@torch.no_grad()
def main():
 torch.set_num_threads(1);torch.distributions.Distribution.set_default_validate_args(False)
 artifacts=ROOT/'learning-runs/semantic-discount-sweep';artifacts.mkdir(exist_ok=True)
 original=ROOT/'branches/semantic-actions-v1/src/learn.cu';source=original.read_text()
 source=source.replace('HD void primitive_transition(', '__device__ float *audit_rewards=nullptr;\nHD void primitive_transition(',1)
 needle='    out[0]=reward; out[1]=clear||death||timeout; out[2]=clear;'
 assert source.count(needle)==1
 source=source.replace(needle,'''#ifdef __CUDA_ARCH__
    if(audit_rewards) audit_rewards[(blockIdx.x*blockDim.x+threadIdx.x)*2048+s.ticks-1]=reward;
#endif
'''+needle)
 source+='\nextern "C" int set_audit_rewards(float *pointer){return cudaMemcpyToSymbol(audit_rewards,&pointer,sizeof(pointer));}\n'
 generated=artifacts/'trace.cu';generated.write_text(source);lib=artifacts/'trace.so'
 subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*FLAGS,'-DCLUMP_MODE=0','-I',str(original.parent),str(generated),'-o',str(lib)],check=True)
 suite=ROOT/'learning-runs/semantic-actions';manifest=json.loads((suite/'manifest.json').read_text());j=manifest['jobs'][0]
 cp=suite/'runs/semantic-seed0/latest.pt';saved=torch.load(cp,map_location='cpu',weights_only=False)
 model=Policy(j['architecture'],j['width']).cuda();model.load_state_dict(saved['model']);model.eval()
 env=Env(1024,24,seed=900000,corpus=pathlib.Path(manifest['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=lib,limit=2048)
 trace=torch.zeros(1024,2048,device='cuda');env.lib.set_audit_rewards.argtypes=[ctypes.c_void_p];env.check(env.lib.set_audit_rewards(trace.data_ptr()))
 previous=json.loads((ROOT/'results/semantic-actions-reward-scores.json').read_text())['results']
 traces={};checks={}
 for key in ['deterministic','sampled_baseline','greedy_baseline','sampled_rest','sampled_rest_wait']:
  env.reset(900000);trace.zero_();torch.manual_seed(900000);start=time.monotonic()
  active=torch.ones(1024,device='cuda',dtype=torch.bool);terminal=torch.zeros_like(env.out)
  for _ in range(2048):
   if not active.any():break
   if key=='deterministic':a=env.heuristic().clone()
   else:
    dist,_=model(env.obs,env.mask);a=dist.sample() if key.startswith('sampled') else dist.probs.argmax(-1)
    if 'rest' in key:a=torch.where(env.mask[:,4]>0,4,a)
    if 'wait' in key:
     h=env.heuristic().clone();a=torch.where(h==3,h,a)
   env.step(a,active=active);ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended];active&=~ended
  assert not active.any();t=terminal.cpu().numpy();traces[key]=trace.cpu().numpy().copy()
  p=previous[key]['episodes'];np.testing.assert_equal(t[:,2],[x['clear'] for x in p]);np.testing.assert_equal(t[:,5],[x['turns'] for x in p])
  actual=traces[key].astype(np.float64)
  np.testing.assert_allclose(actual.sum(1),[x['raw_reward'] for x in p],rtol=1e-6,atol=1e-5)
  np.testing.assert_allclose(actual@(.99**np.arange(2048)),[x['discounted_return'] for x in p],rtol=1e-6,atol=1e-5)
  checks[key]=dict(clears=int(t[:,2].sum()),seconds=time.monotonic()-start)
  print(key,checks[key],flush=True)
 np.savez_compressed(artifacts/'per-turn-rewards.npz',**traces)
 # Fixed grid plus crossing points. Rescoring never changes actions or observations.
 gammas=[.99,.995,.997,.998,.999,.9992,.9995,.9997,.9998,.9999,.99995,1.]
 means={k:v.astype(np.float64).mean(0) for k,v in traces.items()};times=np.arange(2048)
 def score(k,g):return float(means[k]@(g**times))
 crossings={}
 for key in traces:
  if key=='deterministic':continue
  # Scan finely rather than assume a unique monotonic crossing.
  grid=np.linspace(.99,1,1001);diff=np.array([score('deterministic',g)-score(key,g) for g in grid]);roots=[]
  for i in np.where(diff[:-1]*diff[1:]<0)[0]:
   lo,hi=grid[i:i+2];sign=diff[i]
   for _ in range(40):
    mid=(lo+hi)/2;value=score('deterministic',mid)-score(key,mid)
    if value*sign>0:lo=mid
    else:hi=mid
   roots.append(float((lo+hi)/2))
  crossings[key]=roots
 rows=[dict(gamma=g,**{k:score(k,g) for k in traces}) for g in gammas]
 # Paired bootstrap by layout (32 clusters), preserving all 32 placements per map.
 generator=np.random.default_rng(8042);indices=generator.integers(0,32,size=(5000,32));intervals={}
 for g in [.999,.9995,.9999,1.]:
  weights=g**times;returns={k:v.astype(np.float64)@weights for k,v in traces.items()}
  intervals[str(g)]={}
  for k in traces:
   if k=='deterministic':continue
   d=(returns['deterministic']-returns[k]).reshape(32,32).mean(0)
   boot=d[indices].mean(1);intervals[str(g)][k]=dict(mean_difference=float(d.mean()),layout_bootstrap_95_interval=np.quantile(boot,[.025,.975]).tolist())
 report=dict(checkpoint_sha256=digest(cp),original_source_sha256=digest(original),instrumented_library_sha256=digest(lib),script_sha256=digest(pathlib.Path(__file__)),checks=checks,rows=rows,crossings=crossings,paired_layout_bootstrap=intervals,note='Fixed policies rescored on reused validation layouts. A ranking flip is not evidence a newly trained policy will learn recovery or generalize.')
 (ROOT/'results/semantic-actions-discount-sweep.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(rows=rows,crossings=crossings,intervals=intervals),indent=2),flush=True)
if __name__=='__main__':main()
