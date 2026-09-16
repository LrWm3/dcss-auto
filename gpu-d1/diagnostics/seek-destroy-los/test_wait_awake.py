"""Behavioral checks for waiting for visible awake enemies, before retreat overlay."""
import torch
from test_retreat import make

def main():
 torch.set_num_threads(1)
 for rotation in range(4):
  env,p,active,observe,step,cell=make(rotation)
  p.wait_for_awake=True;p.enabled=False
  observe(enemies=((0,-3,True),));assert step()==8 and bool(p.approach_wait[0])
  observe(enemies=((0,-1,True),));assert step()!=8 and not bool(p.approach_wait[0])
  observe(enemies=((0,-3,False),));step();assert not bool(p.approach_wait[0])
  observe(enemies=());env.mask[:,9]=1;assert step()==9
  env.mask[:,9]=0;p.enabled=True
  observe();assert step()!=8 and int(p.events[0,4])==1 and not bool(p.approach_wait[0])
  p.state[0,0]=3;observe();assert step()==8
  active.zero_();step();assert not bool(p.approach_wait[0])
 print('Awake approach-wait tests passed: rotations, adjacent attack, sleeping-only pursuit, rest, retreat priority, lockout waiting, inactive worlds.')
if __name__=='__main__':main()
