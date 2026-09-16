"""Validate clump placement, train seed 0, then evaluate the 2x2 placement screen."""
import ctypes as C
import json
import pathlib
import subprocess
import sys
import time
import torch
import run_ring_ablations as runner
from learn_env_ring_multi import Env

def main():
 root=runner.ROOT.parents[1];start=time.monotonic()
 source=root/'learning-runs/vision15-seen-death4-30m'
 manifest=json.loads((source/'manifest.json').read_text());corpus=pathlib.Path(manifest['corpus'])
 assert runner.corpus_manifest(corpus)==manifest['maps']
 job=dict(manifest['jobs'][0],name='clumps_third',id='clumps_third-seed0',clump_mode=1)
 checks=runner.Store(root/'learning-runs/vision15-clumps-preflight',2*runner.GIB,5*runner.GIB)
 checks.root.mkdir(parents=True,exist_ok=True)
 torch.set_num_threads(1)
 libraries={mode:runner.build(checks,dict(job,clump_mode=mode)) for mode in [0,1,2]}
 audit={}
 for mode,lib in libraries.items():
  env=Env(4096,24,seed=17,corpus=corpus/'train',map_limit=256,map_filter=-2,library_path=lib)
  env.lib.learn_placement_audit.argtypes=[C.c_void_p,C.c_int,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p]
  out=torch.empty((4096,2),dtype=torch.int32,device='cuda')
  env.check(env.lib.learn_placement_audit(env.state.data_ptr(),4096,C.byref(env.config),C.byref(env.tables),out.data_ptr(),env.stream))
  assert (out[:,1]==0).all(),mode
  fraction=out[:,0].float().mean().item()
  assert (mode==0 and fraction==0) or (mode==2 and fraction==1) or (mode==1 and .30<fraction<.37)
  audit[str(mode)]=dict(episodes=4096,clumped_fraction=fraction,placement_checks_passed=True)
  del env,out
 oldlibs=list((source/'build').glob('*.so'));assert len(oldlibs)==1
 a=Env(64,24,seed=900000,corpus=corpus/'validation',map_limit=32,map_filter=-2,library_path=oldlibs[0])
 b=Env(64,24,seed=900000,corpus=corpus/'validation',map_limit=32,map_filter=-2,library_path=libraries[0])
 torch.manual_seed(42)
 for step in range(128):
  assert torch.equal(a.obs,b.obs) and torch.equal(a.mask,b.mask)
  actions=torch.distributions.Categorical(probs=a.mask).sample()
  a.step(actions);b.step(actions)
  assert torch.equal(a.out,b.out)
 audit['ordinary_parity']=dict(episodes=64,steps=128,all_observations_masks_outputs_exact=True)
 del a,b
 result=root/'results/vision15-clumps-preflight.json';result.write_text(json.dumps(audit,indent=2)+'\n')
 print('Placement and ordinary-behavior checks passed',audit,flush=True)
 suite=root/'learning-runs/vision15-clumps-30m'
 subprocess.run([sys.executable,str(runner.ROOT/'scripts/run_ring_ablations.py'),'--output',str(suite),'--steps','30000000','--seeds','0'],check=True)
 actual=json.loads((suite/'manifest.json').read_text());assert actual['jobs']==[job] and actual['maps']==manifest['maps']
 initial=torch.load(suite/'runs/clumps_third-seed0/snapshots/000000000000.pt',weights_only=False,map_location='cpu')['model']
 original=torch.load(root/'learning-runs/vision15-seen-death4-10m/runs/tiles_seen_death4-seed0/snapshots/000000000000.pt',weights_only=False,map_location='cpu')['model']
 assert all(torch.equal(v,original[k]) for k,v in initial.items())
 subprocess.run([sys.executable,str(runner.ROOT/'scripts/evaluate_clumps.py')],check=True)
 curve=json.loads((suite/'runs/clumps_third-seed0/curve.json').read_text())
 report=dict(manifest=actual,preflight=audit,initial_weights_exact=True,curve=curve,wall_seconds=time.monotonic()-start)
 (root/'results/vision15-clumps-30m.json').write_text(json.dumps(report,separators=(',',':'))+'\n')
 print('Complete',report['wall_seconds'],flush=True)
if __name__=='__main__':main()
