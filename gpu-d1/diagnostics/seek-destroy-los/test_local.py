"""Synthetic routing/information-boundary checks; no simulator state supplied."""
from types import SimpleNamespace
import torch
from local_policy import LocalPolicy

def check(side):
 n=7;cells=side*side;player=2*cells+200;frontier=player+4+8*(side//2+1)
 env=SimpleNamespace(batch=n,obs=torch.zeros((n,999 if side==15 else 502),device='cuda'),mask=torch.ones((n,10),device='cuda'),stream=torch.cuda.current_stream().cuda_stream)
 env.obs[:,player+2]=40/80;env.obs[:,player+3]=35/70;env.mask[:,9]=0
 p=LocalPolicy(env,side)
 def floor(i,points):
  for x,y in points:
   j=(y+side//2)*side+x+side//2
   if abs(x)<=side//2 and abs(y)<=side//2:env.obs[i,j]=1
   else:p.memory[i,(35+y)*80+40+x]=1
 def enemy(i,k,x,y,hp):env.obs[i,2*cells+5*k:2*cells+5*k+5]=torch.tensor([x/80,y/70,hp/16,0,1],device='cuda')
 # Choose weakest adjacent visible target (east over north).
 floor(0,[(0,0),(0,-1),(1,0)]);enemy(0,0,0,-1,8);enemy(0,1,1,0,2)
 # Known U-route to an enemy east. Unknown direct middle cell is forbidden.
 floor(1,[(0,0),(0,-1),(1,-2),(2,-1),(2,0)]);enemy(1,0,2,0,8)
 # No visible records: use frontier south, regardless of irrelevant scalars.
 floor(2,[(0,0),(0,1)]);env.obs[2,frontier]=1;env.obs[2,frontier+7+2]=1
 # At anchor: probe specified unknown east neighbor, without floor lookup.
 floor(3,[(0,0)]);env.obs[3,frontier]=1;env.obs[3,frontier+5]=1
 # No reachable visible target and no frontier: wait, never cross unknown.
 floor(4,[(0,0),(2,0)]);enemy(4,0,2,0,8)
 # Inactive row must not change action or memory.
 env.obs[5,:cells]=1
 # Rest uses mask only, not enemy knowledge.
 floor(6,[(0,0)]);env.mask[6,9]=1
 active=torch.ones(n,dtype=torch.bool,device='cuda');active[5]=False
 actions=p(active).clone();torch.cuda.synchronize()
 assert actions.tolist()==[1,0,2,1,8,8,8],actions.tolist()
 assert p.reason[:5].tolist()==[0,1,2,2,4]
 assert not p.memory[5].any()
 assert p.memory[1,35*80+41]==0,'Unknown shortcut became known'
 # Unknown input cannot erase terrain memory; former visible enemy disappears.
 env.obs[1,:cells]=0;env.obs[1,2*cells:2*cells+200]=0
 env.obs[1,frontier]=1;env.obs[1,frontier+7+2]=1
 remembered=p.memory[1].clone();p(active);assert torch.equal(remembered,p.memory[1]);assert int(p.actions[1])==2
 # Explicitly exposing the shortcut changes pursuit from north to NE.
 enemy(1,0,2,0,8);env.obs[1,frontier]=0;floor(1,[(1,-1)])
 p(active);assert int(p.actions[1])==4
 # Rest priority only when enabled; hidden/dead slots are zero.
 p.rest=True;p(active);assert int(p.actions[6])==9
 env.mask[6,9]=0;p(active);assert int(p.actions[6])==8
 print('passed',side,'x',side,flush=True)

if __name__=='__main__':
 torch.set_num_threads(1)
 check(9);check(15)
