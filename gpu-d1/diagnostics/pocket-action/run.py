"""Static action probabilities: no combat steps or sampling."""
import ctypes as C
import importlib.util
import json
import pathlib
import sys
import subprocess
import time
import numpy as np
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'diagnostics'))
from model_selection import select_models, result_path, load_policy
spec=importlib.util.spec_from_file_location('symmetry',ROOT/'diagnostics/pocket-symmetry/run.py')
sym=importlib.util.module_from_spec(spec);spec.loader.exec_module(sym)
Env,Policy,digest=sym.Env,sym.Policy,sym.digest
folder=pathlib.Path(__file__).parent
names=['N','E','S','W','NE','SE','SW','NW','wait']
offsets=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]
def transform(x,y,r,m):
 if m:x=-x
 for _ in range(r):x,y=-y,x
 return x,y

def main():
 started=time.monotonic();torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
 paths=select_models({'ordinary':ROOT/'learning-runs/vision15-seen-death4-30m/runs/tiles_seen_death4-seed0/snapshots/000030015488.pt','mixed':ROOT/'learning-runs/vision15-clumps-30m/runs/clumps_third-seed0/snapshots/000030015488.pt'})
 models={}
 for name,path in paths.items():
  model=load_policy(path,Policy);models[name]=model
 report={'training_performed':False,'simulation_steps':0,'checkpoint_sha256':{k:digest(v) for k,v in paths.items()},'cases':[]}
 reference={}
 for mirror in [0,1]:
  distance=6;build=folder/'build'/str(mirror);build.mkdir(parents=True,exist_ok=True)
  sym.maps(build,distance,mirror,center_pocket=True)
  lib=build/'probe.so'
  flags=[f'-DPOCKET_MIRROR={mirror}',f'-DPOCKET_DISTANCE={distance}','-DCLUMP_MODE=0','-DPROGRESS_INPUT=2','-DKILL_MILLI=1000','-DCLEAR_MILLI=3000','-DDEATH_MILLI=4000','-DFRONTIER_TRAVEL=0','-DOGRE_COUNT=0','-DMONSTER_WAKE_LOS=1','-DTERRAIN_LOS=1','-DGLOBAL_ENEMIES=0','-DLEARN_ENEMIES=40','-DMULTI_MAP','-DSLEEP_ON','-DEXPLORE_REWARD','-DMARK_WALLS','-DEXPLORE_MILLI=2','-DFRONTIER_RING_MEMORY_WALLS_OBS','-DKNOWN_FRONTIER','-DFRONTIER_ROUTE_CUE_OBS','-DFAST_FRONTIER','-DLEARN_BLOCK_SIZE=4','-DCLEAR_PER_ENEMY_MILLI=0']
  subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*flags,str(folder/'probe.cu'),'-o',str(lib)],check=True)
  env=Env(216,24,seed=900000,corpus=build,map_limit=4,library_path=lib)
  env.lib.pocket_init.argtypes=[C.c_void_p,C.c_int,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p]
  env.check(env.lib.pocket_init(env.state.data_ptr(),env.batch,C.byref(env.config),C.byref(env.tables),env.obs.data_ptr(),env.mask.data_ptr(),env.stream))
  obs=env.obs.cpu().numpy();masks=env.mask.cpu().numpy()
  assert (obs[:,225:450]>0).sum(1).tolist()==[1]*216
  assert np.all(masks.sum(1)==2) and np.all(obs[:,718:733]==0)
  assert np.all(obs[:,652]==.5) and np.all(obs[:,653]==.5)
  # Check every feature against an exact spatial transform of the base observation.
  for i,o in enumerate(obs):
   r=i%4;g=i//4
   if mirror==0 and r==0:reference[g]=o.copy()
   base=reference[g];expected=base.copy()
   for start in [0,225,733]:
    for y in range(-7,8):
     for x in range(-7,8):
      xx,yy=transform(x,y,r,mirror);expected[start+(yy+7)*15+xx+7]=base[start+(y+7)*15+x+7]
   ring=[(x,-8) for x in range(-8,9)]+[(x,8) for x in range(-8,9)]+[(-8,y) for y in range(-7,8)]+[(8,y) for y in range(-7,8)]
   for j,(x,y) in enumerate(ring):expected[654+ring.index(transform(x,y,r,mirror))]=base[654+j]
   for j in range(450,650,5):
    x,y=transform(float(base[j])*80,float(base[j+1])*70,r,mirror);expected[j]=x/80;expected[j+1]=y/70
   np.testing.assert_allclose(o,expected,atol=1e-7,rtol=0)
   attack=offsets.index(transform(-1,-1,r,mirror));assert masks[i,attack]==1 and masks[i,8]==1
  with torch.no_grad():probs={name:model(env.obs,env.mask).probs.cpu().tolist() for name,model in models.items()}
  for i in range(216):
   r=i%4;g=i//4;attack=offsets.index(transform(-1,-1,r,mirror))
   report['cases'].append(dict(mirror=mirror,rotation=r,kind=g//9,player_hp=[6,12,18][g//3%3],enemy_hp=['full','half','one'][g%3],attack_direction=names[attack],pocket_direction=names[offsets.index(transform(1,1,r,mirror))],policies={k:dict(wait_probability=v[i][8],attack_probability=v[i][attack],greedy_action=names[int(np.argmax(v[i]))],action_probabilities=v[i]) for k,v in probs.items()}))
  print('finished mirror',mirror,flush=True)
 report['exact_observation_symmetry_verified']=True
 report['source_hashes']={str(p.relative_to(ROOT)):digest(p) for p in [folder/'run.py',folder/'probe.cu',ROOT/'diagnostics/pocket-symmetry/run.py',ROOT/'branches/vision15-clumps-v1/src/learn.cu']}
 report['elapsed_seconds']=time.monotonic()-started
 result_path(ROOT,'pocket-static-actions.json').write_text(json.dumps(report,indent=2)+'\n')
 for case in report['cases']:
  if case['kind']==3 and case['player_hp']==12 and case['enemy_hp']=='full':print(case)
if __name__=='__main__':main()
