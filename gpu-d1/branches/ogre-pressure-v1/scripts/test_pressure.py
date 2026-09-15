"""Check pressure resets, mixed routing, CPU/CUDA parity, and an oracle detour witness.
The witness uses hidden geometry only as an evaluation feasibility check.
"""
import collections,json,pathlib,sys,torch
import numpy as np
from learn_env_ring_multi import Env
from learn_env import ROOT
lib=pathlib.Path(sys.argv[1]);shared=ROOT.parents[1]
args=dict(batch=16,enemies=26,seed=321,corpus=ROOT/'fixtures/pressure/validation',map_limit=16,map_filter=-2,pressure_only=True,library_path=lib)
a=Env(device='cpu',**args);b=Env(device='cuda',**args)
assert (a.obs[:,162+4:362:5].sum(1)==2).all()
for step in range(256):
 assert torch.equal(a.obs,b.obs.cpu()) and torch.equal(a.mask,b.mask.cpu())
 action=a.heuristic().clone();a.step(action);b.step(action.cuda())
 assert torch.equal(a.out,b.out.cpu())
 assert (a.out[:,18]==1).all() and (a.out[:,20]==1).all()
 assert ((a.out[:,19]>=0)&(a.out[:,19]<16)).all()
 if step==0:assert torch.equal(a.out[:,19],torch.arange(16).float())
 assert (a.out[:,3]<=1).all()
# Ordinary mode must not select pressure maps, even though they are loaded.
e=Env(batch=64,enemies=26,seed=55,device='cpu',corpus=shared/'fixtures/d1-corpus-388/train',map_limit=2,pressure_corpus=ROOT/'fixtures/pressure/train',pressure_permille=0,library_path=lib)
e.step(e.heuristic());assert (e.out[:,18]==0).all()
# Large initial batch tests reset mixture without policy-dependent episode lengths.
e=Env(batch=2048,enemies=26,seed=55,device='cpu',corpus=shared/'fixtures/d1-corpus-388/train',map_limit=2,pressure_corpus=ROOT/'fixtures/pressure/train',pressure_permille=100,library_path=lib)
e.step(e.heuristic());fraction=e.out[:,18].mean().item();assert .07<fraction<.13,fraction
print('PASS: pressure roster/goal and scenario labels, CPU/CUDA parity, and 10% reset mixture:',fraction,flush=True)

D=((0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1))
def plan(obs,floor):
 px=int(round(float(obs[364])*80));py=int(round(float(obs[365])*70));p=py*80+px
 target=p+int(round(float(obs[162])*80))+80*int(round(float(obs[163])*70))
 q=p+int(round(float(obs[282])*80))+80*int(round(float(obs[283])*70))
 qlive=bool(obs[286]);start=p
 def near(z):return max(abs(z%80-q%80),abs(z//80-q//80))
 queue=collections.deque([p]);first={p:8}
 while queue:
  x=queue.popleft()
  if x==target:return first[x]
  for d,(dx,dy) in enumerate(D):
   xx,yy=x%80+dx,x//80+dy
   if not(0<=xx<80 and 0<=yy<70):continue
   z=yy*80+xx
   if floor[z] and z not in first and (not qlive or near(z)>2):
    first[z]=d if x==start else first[x];queue.append(z)
 # If the monster is still beside the ogre, retreat and let it separate.
 candidates=[]
 for d,(dx,dy) in enumerate(D):
  x,y=px+dx,py+dy
  if 0<=x<80 and 0<=y<70 and floor[y*80+x]:candidates.append((near(y*80+x),d))
 return max(candidates)[1] if candidates else 8

rows=[]
for split,n in [('train',32),('validation',16)]:
 env=Env(batch=n,enemies=26,seed=900000,device='cpu',corpus=ROOT/'fixtures/pressure'/split,map_limit=n,map_filter=-2,pressure_only=True,library_path=lib)
 floor=env.arrays[0].numpy().reshape(n,5600);active=torch.ones(n,dtype=torch.bool);terminal=torch.zeros_like(env.out)
 for step in range(1024):
  action=torch.tensor([plan(env.obs[i],floor[i]) if active[i] else 8 for i in range(n)])
  env.step(action,active=active);ended=active & (env.out[:,1]>0);terminal[ended]=env.out[ended];active &= ~ended
  if not active.any():break
 assert not active.any()
 for i,m in enumerate(env.metadata):rows.append(dict(scenario_id=m['scenario_id'],family=m['family'],split=split,clear=bool(terminal[i,2]),ogre_damage=float(terminal[i,9]),ogres_alive=int(terminal[i,13])))
(ROOT/'fixtures/pressure-witness.json').write_text(json.dumps(rows,indent=2)+'\n')
print('Oracle witness:',sum(r['clear'] for r in rows),'/',len(rows),'clears;',sum(r['clear'] and r['ogre_damage']==0 for r in rows),'without ogre damage',flush=True)
assert all(r['clear'] for r in rows),'A scenario lacks a successful dynamic witness'
