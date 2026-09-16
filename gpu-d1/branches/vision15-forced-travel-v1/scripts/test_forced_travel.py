"""Forced-action masks, physical/decision deadlines, rewards and CPU/CUDA parity."""
import ctypes as C
import json
from pathlib import Path
import resource
import sys
import numpy as np
import torch
from learn_env_ring_multi import Env
from run_ring_ablations import ROOT,library_key
resource.setrlimit(resource.RLIMIT_CORE,(0,0));torch.set_num_threads(1)
suite=Path(sys.argv[1]);jobs=json.loads((suite/'manifest.json').read_text())['jobs']
assert len({library_key(j) for j in jobs}) == len(jobs), 'Budget variants must use distinct native libraries'
for job in jobs:
    travel=job['frontier_travel']
    args=dict(batch=8,enemies=24,seed=137,map_limit=2,limit=512,
              corpus=ROOT.parents[1]/'fixtures/d1-corpus-388/train',library_path=suite/'build'/(library_key(job)+'.so'))
    a,b=Env(device='cpu',**args),Env(device='cuda',**args)
    assert a.obs.shape[1]==958 and a.action_size==9+travel
    for name in ['learn_semantic_test','learn_ogre_test','learn_travel_test','learn_forced_budget_test']:
        fn=getattr(a.lib,name);fn.argtypes=[C.c_void_p,C.c_void_p];a.check(fn(C.byref(a.config),C.byref(a.tables)))
    kills=ticks=torch.zeros(8);floors=(a.obs[:,:225]==1).float().sum(1)
    uses=turns=0; decisions=torch.zeros(8); timeouts=0; torch.manual_seed(412)
    for step in range(1050):
        assert torch.equal(a.obs,b.obs.cpu()) and torch.equal(a.mask,b.mask.cpu()),step
        forced=a.mask[:,9]>0
        assert (a.mask[forced,:9]==0).all()
        assert not (forced & (a.obs[:,225:450]>0).any(1)).any()
        action=torch.multinomial(a.mask,1).squeeze(1)
        assert (action[forced]==9).all()
        decisions+=1
        a.step(action);b.step(action.cuda());out=a.out;done=out[:,1]>0
        assert torch.equal(out,b.out.cpu()),(step,'output')
        assert torch.equal(out[:,5]-ticks,out[:,26])
        assert torch.equal(a.obs[:,651],torch.where(done,0,(decisions if job['decision_limit'] else out[:,5])/512)), (step,a.obs[:,651],decisions,out[:,5],done)
        timed=out[:,7]>0; timeouts+=timed.sum().item()
        assert ((decisions if job['decision_limit'] else out[:,5])[timed]==512).all()
        if job['decision_limit']: assert (decisions<=512).all()
        else: assert (out[:,5]<=512).all()
        decisions=torch.where(done,0,decisions)
        expected=out[:,3]-kills+.002*(out[:,13]-floors)-.001*out[:,26]+3*out[:,2]-out[:,6]
        assert torch.allclose(out[:,0],expected,atol=1e-5,rtol=0),(step,'reward')
        assert torch.equal(out[:,9]+out[:,10],24-out[:,3])
        assert (out[:,14:26]==0).all() and (out[:,32]==0).all()
        assert torch.equal(out[:,1],out[:,2]+out[:,6]+out[:,7])
        ticks=torch.where(done,0,out[:,5]).clone();kills=torch.where(done,0,out[:,3]).clone()
        floors=torch.where(done,(a.obs[:,:225]==1).float().sum(1),out[:,13]).clone()
        uses+=out[:,27].sum().item();turns+=out[:,26].sum().item()
        if step%40==0:
            saved=[v.clone() for v in [a.state,a.obs,a.mask,a.out]]
            a.step(action,active=torch.zeros(8,dtype=torch.bool))
            assert all(torch.equal(x,y) for x,y in zip(saved,[a.state,a.obs,a.mask,a.out]))
    assert (uses>0 and turns>8400) if travel else (uses==0 and turns==8400)
    print(job['id'],'timeouts',int(timeouts),'PASS: 8400 policy transitions;',int(turns),'physical turns;',int(uses),'travel uses; native semantics, rewards, expanded clock, active masks',flush=True)


# The physical-budget arm changes action availability only: identical actions
# must reproduce the original optional-travel environment exactly.
original=ROOT.parents[1]/'learning-runs/vision15-frontier-30m'
original_lib=next((original/'build').glob('*travel1.so'))
job=next(j for j in jobs if not j['decision_limit'])
args=dict(batch=8,enemies=24,seed=137,map_limit=2,limit=512,device='cpu',
          corpus=ROOT.parents[1]/'fixtures/d1-corpus-388/train')
a=Env(library_path=suite/'build'/(library_key(job)+'.so'),**args)
b=Env(library_path=original_lib,**args)
for step in range(1050):
    assert torch.equal(a.obs,b.obs)
    available=b.mask[:,9]>0
    assert torch.equal(a.mask[:,9],b.mask[:,9])
    assert (a.mask[available,:9]==0).all()
    assert torch.equal(a.mask[~available],b.mask[~available])
    action=torch.multinomial(a.mask,1).squeeze(1)
    a.step(action); b.step(action)
    assert torch.equal(a.out,b.out)
print('PASS: 8400 identical-action transitions match original optional-travel dynamics and observations',flush=True)
