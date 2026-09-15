"""Trajectory-level regression of optimized nearest-frontier observations."""
import pathlib,torch
from learn_env_ring_multi import Env
from learn_env import ROOT
base=ROOT/'learning-runs/ring-route-cue-corrected-200m-seed0/build/ring-reward2-frontier1-route1.so'
fast=ROOT/'performance/learn_fast_b4.so'
args=dict(batch=8,enemies=40,seed=123,device='cpu',map_limit=4,corpus=ROOT/'fixtures/d1-corpus-388/validation')
a=Env(library_path=base,**args);b=Env(library_path=fast,**args)
for turn in range(1200):
    assert torch.equal(a.obs,b.obs),('obs',turn)
    assert torch.equal(a.mask,b.mask),('mask',turn)
    action=a.heuristic().clone()
    _,outa=a.step(action);_,outb=b.step(action)
    assert torch.equal(outa,outb),('out',turn)
print('PASS: 1200 steps x 8 worlds, unchanged observations, masks and transitions')

# An evaluation world that has already finished must consume no simulator RNG
# and leave its state and output buffers untouched. Other worlds still advance.
a.reset(456);b.reset(456)
a.out.zero_();b.out.zero_()
active=torch.arange(b.batch)%2==0
before=[x.clone() for x in (b.state,b.obs,b.mask,b.out)]
actions=a.heuristic().clone()
a.step(actions);b.step(actions,active=active)
for old,actual,reference in zip(before,(b.state,b.obs,b.mask,b.out),(a.state,a.obs,a.mask,a.out)):
    assert torch.equal(actual[~active],old[~active]),'inactive world changed'
    assert torch.equal(actual[active],reference[active]),'active world differs'
print('PASS: inactive worlds frozen; active worlds match ordinary stepping')
