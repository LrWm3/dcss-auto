from types import SimpleNamespace
import torch
from retreat_policy import RetreatPolicy

def make(rotation=0):
 env=SimpleNamespace(batch=1,obs=torch.zeros((1,999),device='cuda'),mask=torch.ones((1,10),device='cuda'),stream=torch.cuda.current_stream().cuda_stream)
 env.mask[:,9]=0;p=RetreatPolicy(env);active=torch.ones(1,dtype=torch.bool,device='cuda')
 def rotate(x,y):
  for _ in range(rotation):x,y=-y,x
  return x,y
 def cell(x,y):
  x,y=rotate(x,y);return (35+y)*80+40+x
 for y in range(-4,2):
  for x in range(-3,4):p.base.memory[0,cell(x,y)]=1
 for y in range(2,6):p.base.memory[0,cell(0,y)]=1
 for y in range(2,5):
  for x in (-1,1):p.base.memory[0,cell(x,y)]=-1
 def observe(player=(0,0),enemies=((-1,-2,True),(1,-2,True))):
  x,y=rotate(*player);env.obs.zero_();env.obs[0,652:654]=torch.tensor([(40+x)/80,(35+y)/70],device='cuda')
  for k,(ex,ey,awake) in enumerate(enemies):
   ex,ey=rotate(ex,ey);env.obs[0,450+5*k:455+5*k]=torch.tensor([(ex-x)/80,(ey-y)/70,(k+2)/16,0,1],device='cuda');env.obs[0,959+k]=-1 if awake else 1
 def step():
  a=p(active);torch.cuda.synchronize();return int(a[0])
 observe();return env,p,active,observe,step,cell

def main():
 torch.set_num_threads(1)
 for rotation,direction in enumerate([2,3,0,1]):
  env,p,active,observe,step,cell=make(rotation)
  assert step()==direction and p.state[0].tolist()==[1,cell(0,3)]
  assert int(p.events[0,0])==1
  for y in (1,2):observe((0,y));assert step()==direction
  observe((0,3));assert step()==8 and int(p.state[0,0])==2 and int(p.events[0,1])==1
  observe((0,3),((0,2,True),(0,0,True)));step();assert int(p.state[0,0])==3 and int(p.events[0,5])==1
  observe((0,0));step();assert int(p.state[0,0])==3 and int(p.events[0,0])==0
  observe((0,0),());step();assert int(p.state[0,0])==0
  observe();step();assert int(p.events[0,0])==1
 # Enemy obstructs the actual next retreat step, even if asleep.
 env,p,active,observe,step,cell=make();step()
 observe((0,1),((-1,-2,True),(1,-2,True),(0,2,False)))
 step();assert int(p.events[0,2])==1 and int(p.state[0,0])==3
 observe();step();assert int(p.events[0,0])==0 and int(p.state[0,0])==3
 # One awake foe does not trigger; missing wall knowledge cannot qualify.
 env,p,active,observe,step,cell=make();observe(enemies=((-1,-2,True),(1,-2,False)));step();assert int(p.state[0,0])==0
 observe();p.base.memory[0,cell(-1,3)]=0;step();assert int(p.events[0,0])==0 and int(p.events[0,7])==1
 # A hallway toward the foes is rejected.
 env,p,active,observe,step,cell=make();observe(enemies=((0,4,True),(0,5,True)));step();assert int(p.events[0,0])==0
 # Adjacency alone does not cancel retreat: only an enemy on the next step.
 env,p,active,observe,step,cell=make();observe(enemies=((-1,0,True),(-1,-1,True)));assert step()==2 and int(p.events[0,4])==1
 # A currently occupied hallway is already a valid holding position, all axes.
 for dx,dy in [(1,0),(0,1),(1,1),(1,-1)]:
  env,p,active,observe,step,cell=make();p.base.memory.zero_();p.base.memory[0,cell(0,0)]=1
  for x in (-1,0,1):
   for y in (-1,0,1):
    if x or y:p.base.memory[0,cell(x,y)]=1 if (x,y) in [(dx,dy),(-dx,-dy)] else -1
  observe(enemies=((3*dx,3*dy,True),(4*dx,4*dy,True)))
  assert step()==8 and int(p.state[0,0])==2
 # A bump into an unseen blocker is inferred from failed movement only.
 env,p,active,observe,step,cell=make();step();p.after_step(torch.zeros_like(active));assert int(p.state[0,0])==3 and int(p.events[0,10])==1
 # No enemies resets state and permits normal rest. Inactive state stays frozen.
 env,p,active,observe,step,cell=make();step();observe(enemies=());env.mask[:,9]=1
 assert step()==9 and int(p.state[0,0])==0
 state=p.state.clone();memory=p.base.memory.clone();active.zero_();step();assert torch.equal(state,p.state) and torch.equal(memory,p.base.memory)
 print('Retreat tests passed: rotations, diagonal halls, away direction, unknown walls, sleep gating, arrival/hold/combat, blocked-route lockout/reset, rest and inactive state.',flush=True)

if __name__=='__main__':main()
