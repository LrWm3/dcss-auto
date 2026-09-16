"""Verify 2048-turn clocks/deadlines and unchanged game dynamics."""
import ctypes as C
import json
import pathlib
import resource
import sys

import torch

from learn_env_ring_multi import Env
from run_ring_ablations import ROOT,library_key

resource.setrlimit(resource.RLIMIT_CORE,(0,0))
torch.set_num_threads(1)
suite=pathlib.Path(sys.argv[1])
job=json.loads((suite/'manifest.json').read_text())['jobs'][0]
args=dict(batch=8,enemies=24,seed=137,map_limit=2,limit=2048,
          corpus=ROOT.parents[1]/'fixtures/d1-corpus-388/train')
lib=suite/'build'/(library_key(job)+'.so')
a,b=Env(device='cpu',library_path=lib,**args),Env(device='cuda',library_path=lib,**args)
original=next((ROOT.parents[1]/'learning-runs/vision15-frontier-30m/build').glob('*travel0.so'))
reference=Env(device='cpu',library_path=original,**args)
for name in ['learn_semantic_test','learn_ogre_test','learn_budget2048_test']:
    fn=getattr(a.lib,name);fn.argtypes=[C.c_void_p,C.c_void_p]
    a.check(fn(C.byref(a.config),C.byref(a.tables)))
assert a.obs.shape[1]==958 and a.action_size==9
ticks=torch.zeros(8);kills=torch.zeros(8)
floors=(a.obs[:,:225]==1).float().sum(1)
torch.manual_seed(412)
for step in range(2200):
    assert torch.equal(a.obs,b.obs.cpu()) and torch.equal(a.mask,b.mask.cpu())
    expected=reference.obs.clone();expected[:,651]/=4
    assert torch.equal(a.obs,expected) and torch.equal(a.mask,reference.mask)
    action=a.heuristic().clone() if step%2 else torch.multinomial(a.mask,1).squeeze(1)
    a.step(action);b.step(action.cuda());reference.step(action)
    out=a.out;done=out[:,1]>0
    assert torch.equal(out,b.out.cpu()) and torch.equal(out,reference.out)
    assert torch.equal(out[:,5]-ticks,out[:,26])
    assert (out[:,5]<=2048).all() and (out[out[:,7]>0,5]==2048).all()
    assert torch.equal(a.obs[:,651],torch.where(done,0,out[:,5]/2048))
    reward=out[:,3]-kills+.002*(out[:,13]-floors)-.001*out[:,26]+3*out[:,2]-out[:,6]
    assert torch.allclose(out[:,0],reward,atol=1e-5,rtol=0)
    assert (out[:,14:26]==0).all() and (out[:,27:33]==0).all()
    ticks=torch.where(done,0,out[:,5]).clone();kills=torch.where(done,0,out[:,3]).clone()
    floors=torch.where(done,(a.obs[:,:225]==1).float().sum(1),out[:,13]).clone()
    if step%64==0:
        saved=[v.clone() for v in [a.state,a.obs,a.mask,a.out]]
        a.step(action,active=torch.zeros(8,dtype=torch.bool))
        assert all(torch.equal(x,y) for x,y in zip(saved,[a.state,a.obs,a.mask,a.out]))
print('PASS: 17,600 CPU/CUDA transitions; original dynamics match exactly; rewards, active masks and normalized clock agree; explicit 512/2047/2048 boundary tests pass.',flush=True)
