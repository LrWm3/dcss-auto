"""15x15 LOS, expanded schema, CPU/CUDA, and optional travel checks."""
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
for job in jobs:
    travel=job['frontier_travel']
    args=dict(batch=8,enemies=24,seed=137,map_limit=2,limit=512,
              corpus=ROOT.parents[1]/'fixtures/d1-corpus-388/train',library_path=suite/'build'/(library_key(job)+'.so'))
    a,b=Env(device='cpu',**args),Env(device='cuda',**args)
    assert a.obs.shape[1]==958 and a.action_size==9+travel
    for name in ['learn_semantic_test','learn_ogre_test','learn_travel_test']:
        fn=getattr(a.lib,name);fn.argtypes=[C.c_void_p,C.c_void_p];a.check(fn(C.byref(a.config),C.byref(a.tables)))
    kills=ticks=torch.zeros(8);floors=(a.obs[:,:225]==1).float().sum(1)
    uses=turns=0;torch.manual_seed(412)
    for step in range(1050):
        assert torch.equal(a.obs,b.obs.cpu()) and torch.equal(a.mask,b.mask.cpu()),step
        action=a.heuristic().clone() if step%2 else torch.randint(0,9,(8,))
        if travel and step%3==0:action=torch.where(a.mask[:,9]>0,9,action)
        a.step(action);b.step(action.cuda());out=a.out;done=out[:,1]>0
        assert torch.equal(out,b.out.cpu()),(step,'output')
        assert torch.equal(out[:,5]-ticks,out[:,26])
        assert torch.equal(a.obs[:,651],torch.where(done,0,out[:,5]/512))
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
    print(job['id'],'PASS: 8400 policy transitions;',int(turns),'physical turns;',int(uses),'travel uses; native semantics, rewards, expanded clock, active masks',flush=True)

# Same primitive actions must have identical dynamics and observations across
# the two action sets. Check the expanded view directly against the packed LOS.
args=dict(batch=8,enemies=24,seed=71,map_limit=2,map_filter=0,limit=512,device='cpu',corpus=ROOT.parents[1]/'fixtures/d1-corpus-388/train')
a=Env(library_path=suite/'build'/(library_key(jobs[0])+'.so'),**args)
b=Env(library_path=suite/'build'/(library_key(jobs[1])+'.so'),**args)
assert a.action_size==9 and b.action_size==10
raw=a.arrays[6].numpy().view(np.uint32).reshape(-1,5600,10)[0]
terrain=a.arrays[0].numpy().reshape(-1,5600)[0]
known=np.zeros((8,5600),dtype=np.float32);seen_extended=0
for step in range(128):
    assert torch.equal(a.obs,b.obs) and torch.equal(a.mask,b.mask[:,:9])
    obs=a.obs.numpy()
    for i in range(8):
        px=int(round(obs[i,652]*80));py=int(round(obs[i,653]*70));origin=py*80+px
        for dy in range(-7,8):
            for dx in range(-7,8):
                x,y=px+dx,py+dy;j=(dy+7)*15+dx+7
                bit=(dy+8)*17+dx+8
                visible=0<=x<80 and 0<=y<70 and bool((raw[origin,bit//32]>>np.uint32(bit%32))&np.uint32(1))
                assert obs[i,733+j]==visible
                if visible:
                    known[i,y*80+x]=1 if terrain[y*80+x] else -1
                    seen_extended+=max(abs(dx),abs(dy))>4
                expected=known[i,y*80+x] if 0<=x<80 and 0<=y<70 else 0
                assert obs[i,j]==expected
        ring=[]
        for dy in [-8,8]:
            for dx in range(-8,9):ring.append((dx,dy))
        for dx in [-8,8]:
            for dy in range(-7,8):ring.append((dx,dy))
        assert len(ring)==64
        for j,(dx,dy) in enumerate(ring):
            x,y=px+dx,py+dy
            expected=known[i,y*80+x] if 0<=x<80 and 0<=y<70 else 0
            assert obs[i,654+j]==expected,('ring',j)
    action=a.heuristic().clone();a.step(action);b.step(action)
    assert torch.equal(a.out,b.out)
    known[a.out[:,1].numpy()>0]=0
assert seen_extended>0
print('PASS: matched primitive trajectories; direct 15x15 LOS/remembered-terrain/radius-8 ring checks;',seen_extended,'visible cells beyond radius four',flush=True)
