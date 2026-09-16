"""Read-only six-enemy, distant visible diagonal pocket retreat diagnostic for the two 30M policies."""
import argparse
import ctypes as C
import collections
import json
import pathlib
import struct
import subprocess
import sys
import time
import numpy as np
import torch
from torch import nn
from torch.distributions import Categorical
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'diagnostics'))
from model_selection import select_models, result_path, load_policy
sys.path.insert(0,str(ROOT/'branches/vision15-clumps-v1/scripts'))
from learn_env_ring_multi import Env
from run_ring_ablations import digest


def maps(folder,distance,mirror,center_pocket=False):
 # Same native ray definition used by the corpus compiler, evaluated on test geometry.
 lines=iter((ROOT/'fixtures/native-1057.rays').read_text().splitlines());ends=[tuple(map(int,next(lines).split())) for _ in range(int(next(lines)))];blockers=[]
 for line in lines:
  x,y,inside,bits=line.split()
  if int(inside):blockers.append((int(x),int(y),int(bits[::-1],2)))
 for r in range(4):
  floor=np.zeros(5600,np.uint8)
  def pos(x,y):
   if center_pocket:x-=distance;y-=distance
   if mirror:x=-x
   for _ in range(r):x,y=-y,x
   return (35+y)*80+40+x
  for x,y in [(x,y) for y in range(-3,distance) for x in range(1-distance,distance)]+[(distance,distance)]:floor[pos(x,y)]=1
  # Unreachable padding allows the original terminal auto-reset to place 24 enemies.
  # It is never visible/reachable in the test, and contains no live test enemies.
  for y in range(5,11):
   for x in range(5,11):floor[y*80+x]=1
  cells=np.flatnonzero(floor);index=np.full(5600,-1,np.int16);index[cells]=np.arange(len(cells))
  distances=np.full((len(cells),5600),65535,np.uint16)
  offsets=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]
  for j,origin in enumerate(cells):
   distances[j,origin]=0;q=collections.deque([origin])
   while q:
    p=q.popleft()
    for dx,dy in offsets:
     x,y=p%80+dx,p//80+dy
     if 0<=x<80 and 0<=y<70:
      dest=y*80+x
      if floor[dest] and distances[j,dest]==65535:distances[j,dest]=distances[j,p]+1;q.append(dest)
  masks=np.zeros((5600,10),np.uint32)
  for p in cells:
   px,py=p%80,p//80;seen=1<<144
   for sx,sy in [(1,1),(-1,1),(-1,-1),(1,-1)]:
    dead=0
    for x,y,bits in blockers:
     qx,qy=px+sx*x,py+sy*y
     if 0<=qx<80 and 0<=qy<70 and not floor[qy*80+qx]:dead|=bits
    for i,(x,y) in enumerate(ends):
     qx,qy=px+sx*x,py+sy*y
     if not(dead>>i)&1 and 0<=qx<80 and 0<=qy<70 and any(x==bx and y==by for bx,by,_ in blockers):seen|=1<<((sy*y+8)*17+sx*x+8)
   masks[p]=[(seen>>(32*i))&0xffffffff for i in range(10)]
  padded=np.full(5600,-1,np.int16);padded[:len(cells)]=cells
  path=folder/f'map-{r}.bin'
  with path.open('wb') as f:
   f.write(struct.pack('<3I4i',0x44325650,r,len(cells),18,681,794,906))
   for a in [floor,padded,index,distances,masks]:f.write(a.tobytes())

class Policy(nn.Module):
 def __init__(self):
  super().__init__();self.body=nn.Sequential(nn.Linear(959,128),nn.Tanh(),nn.Linear(128,128),nn.Tanh());self.actor=nn.Linear(128,9);self.critic=nn.Linear(128,1)
 def forward(self,o,m):return Categorical(logits=self.actor(self.body(o)).masked_fill(m==0,-1e9))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--distance',type=int,choices=[2,4,6],required=True);ap.add_argument('--mirror',type=int,choices=[0,1],required=True);args=ap.parse_args();distance=args.distance;mirror=args.mirror
 started=time.monotonic();torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
 folder=pathlib.Path(__file__).parent;build=folder/'build'/f'{distance}-{mirror}';build.mkdir(parents=True,exist_ok=True);maps(build,distance,mirror)
 lib=build/'diagonal_pocket.so'
 flags=[f'-DPOCKET_MIRROR={mirror}',f'-DPOCKET_DISTANCE={distance}','-DCLUMP_MODE=0','-DPROGRESS_INPUT=2','-DKILL_MILLI=1000','-DCLEAR_MILLI=3000','-DDEATH_MILLI=4000','-DFRONTIER_TRAVEL=0','-DOGRE_COUNT=0','-DMONSTER_WAKE_LOS=1','-DTERRAIN_LOS=1','-DGLOBAL_ENEMIES=0','-DLEARN_ENEMIES=40','-DMULTI_MAP','-DSLEEP_ON','-DEXPLORE_REWARD','-DMARK_WALLS','-DEXPLORE_MILLI=2','-DFRONTIER_RING_MEMORY_WALLS_OBS','-DKNOWN_FRONTIER','-DFRONTIER_ROUTE_CUE_OBS','-DFAST_FRONTIER','-DLEARN_BLOCK_SIZE=4','-DCLEAR_PER_ENEMY_MILLI=0']
 subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*flags,str(folder/'probe.cu'),'-o',str(lib)],check=True)
 env=Env(24*512,24,seed=900000,corpus=build,map_limit=4,library_path=lib)
 p=C.c_void_p;i=C.c_int;env.lib.hall_init.argtypes=[p,i,p,p,C.c_uint64,p,p,p];env.lib.hall_control.argtypes=[p,i,p,p,i,p];env.lib.hall_status.argtypes=[p,i,p,p,p]
 report=dict(distance=distance,mirror=mirror,training_performed=False,rollouts_per_condition=512,rollout_limit=256,initial_tick=256,source_hashes={str(q.relative_to(ROOT)):digest(q) for q in [folder/'run.py',folder/'probe.cu',ROOT/'fixtures/native-1057.rays',ROOT/'branches/vision15-clumps-v1/src/learn.cu',ROOT/'branches/vision15-clumps-v1/src/sim.h']},conditions=[dict(kind='weak' if g<12 else 'tough',hp=[6,12,18][g//4%3],rotation=g%4) for g in range(24)],arms={})
 paths=select_models({'ordinary':ROOT/'learning-runs/vision15-seen-death4-30m/runs/tiles_seen_death4-seed0/snapshots/000030015488.pt','mixed':ROOT/'learning-runs/vision15-clumps-30m/runs/clumps_third-seed0/snapshots/000030015488.pt'})
 back=torch.tensor([4+(1+mirror+(j//512)%4)%4 for j in range(env.batch)],device='cuda')
 for arm in ['retreat_fight','ordinary_force_route','mixed_force_route']:
  env.check(env.lib.hall_init(env.state.data_ptr(),env.batch,C.byref(env.config),C.byref(env.tables),900000,env.obs.data_ptr(),env.mask.data_ptr(),env.stream))
  assert (env.mask.gather(1,back[:,None])==1).all()
  # Six visible enemies, local geometry through unchanged LOS, all nine actions available.
  assert (env.obs[:,225:450].gt(0).sum(1)==6).all()
  assert (env.mask.sum(1)==9).all()
  initial_seen=env.obs[:,958].reshape(24,512).mean(1).mul(1024).tolist()
  assert torch.all(env.obs[:,958]==((2*distance-1)*(distance+3)+1)/1024)
  # Target floor and current-visibility channels must both show the pocket.
  for rotation in range(4):
   x=-distance if mirror else distance;y=distance
   for _ in range(rotation):x,y=-y,x
   index=(y+7)*15+x+7;rows=torch.arange(env.batch,device='cuda')//512%4==rotation
   assert (env.obs[rows,index]==1).all() and (env.obs[rows,733+index]==1).all()
  active=torch.ones(env.batch,dtype=torch.bool,device='cuda');won=torch.zeros_like(active);dead=torch.zeros_like(active);turns=torch.zeros(env.batch,device='cuda')
  reached=torch.zeros_like(active);attack_before=torch.zeros_like(active);first_reach=torch.zeros(env.batch,device='cuda');status=torch.empty((env.batch,4),dtype=torch.int32,device='cuda')
  left_pocket=torch.zeros_like(active);left_before_fight=torch.zeros_like(active);fought_in_pocket=torch.zeros_like(active)
  pocket_contact=torch.zeros(env.batch,device='cuda');pocket_attack=torch.zeros_like(pocket_contact);pocket_wait=torch.zeros_like(pocket_contact)
  first=None;checkpoint=None
  if arm not in ['hold_fight','retreat_fight']:
   path=paths[arm.split('_')[0]];model=load_policy(path,Policy);checkpoint=digest(path)
   with torch.no_grad():
    dist=model(env.obs,env.mask);first=dict(retreat_probability=dist.probs.gather(1,back[:,None]).reshape(24,512).mean(1).tolist(),greedy_retreat=(dist.probs.argmax(1)==back).reshape(24,512).float().mean(1).tolist(),away_probability=torch.stack([dist.probs[j,[2,5,6] if (j//512)%4==0 else [3,6,7] if (j//512)%4==1 else [0,4,7] if (j//512)%4==2 else [1,4,5]].sum() for j in range(env.batch)]).reshape(24,512).mean(1).tolist())
  torch.manual_seed(900000)
  with torch.no_grad():
   for step in range(256):
    if arm in ['hold_fight','retreat_fight']:
     env.check(env.lib.hall_control(env.state.data_ptr(),env.batch,C.byref(env.config),env.actions.data_ptr(),int(arm=='retreat_fight'),env.stream));actions=env.actions
    else:
     actions=model(env.obs,env.mask).sample()
     if step==0 and arm.endswith('force_retreat'):actions=back
     if step<distance and arm.endswith('force_route'):actions=back
    env.check(env.lib.hall_status(env.state.data_ptr(),env.batch,actions.data_ptr(),status.data_ptr(),env.stream))
    here=active & (status[:,0]>0)
    contact=here & (status[:,2]>0);pocket_contact+=contact;pocket_attack+=contact & (status[:,1]>0);pocket_wait+=contact & (status[:,3]>0)
    departed=active & reached & ~here;left_pocket |= departed;left_before_fight |= departed & ~fought_in_pocket
    fought_in_pocket |= here & (status[:,1]>0)
    new=here & ~reached;first_reach[new]=step;reached |= here
    attack_before |= active & ~reached & (status[:,1]>0)
    env.step(actions,active=active);turns+=active
    won|=active&(env.out[:,2]>0);dead|=active&(env.out[:,6]>0);active &= env.out[:,1]==0
    if not active.any():break
  def means(x):return x.float().reshape(24,512).mean(1).tolist()
  report['arms'][arm]=dict(initial_seen_floor_count=initial_seen,first=first,checkpoint_sha256=checkpoint,win=means(won),death=means(dead),unresolved=means(active),turns=means(turns),pocket_contact_turns=means(pocket_contact),pocket_attack_turns=means(pocket_attack),pocket_wait_turns=means(pocket_wait),reached_pocket=means(reached),left_pocket_after_arrival=means(left_pocket),left_pocket_before_fighting_there=means(left_before_fight),attacked_before_pocket=means(attack_before),mean_first_reach_turn=[float(first_reach.reshape(24,512)[j][reached.reshape(24,512)[j]].mean()) if reached.reshape(24,512)[j].any() else None for j in range(24)])
  report['elapsed_seconds']=time.monotonic()-started
  result_path(ROOT,f'pocket-symmetry-{distance}-mirror{mirror}.json').write_text(json.dumps(report,indent=2)+'\n')
  print(arm,'win',means(won),'unresolved',int(active.sum()),flush=True)
if __name__=='__main__':main()
