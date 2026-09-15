"""Check both physical-turn budgets and zero/two-ogre travel combinations."""
import ctypes as C
import json
from pathlib import Path
import resource
import sys
import torch
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
branch, suite = map(lambda s:Path(s).resolve(),sys.argv[1:3])
sys.path.insert(0,str(branch/'scripts'))
from learn_env_ring_multi import Env
from run_ring_ablations import library_key
job=json.loads((suite/'manifest.json').read_text())['jobs'][0]
travel=job.get('frontier_travel',False); limit=job['turn_limit']; count=job['enemies']
torch.set_num_threads(1)
args=dict(batch=8,enemies=count,seed=137,map_limit=2,limit=limit,
          corpus=branch.parents[1]/'fixtures/d1-corpus-388/train',
          library_path=suite/'build'/(library_key(job)+'.so'))
a,b=Env(device='cpu',**args),Env(device='cuda',**args)
assert a.obs.shape[1]==502 and a.action_size==9+travel
for name in ['learn_semantic_test','learn_ogre_test','learn_travel_test','learn_deadline_test']:
    if hasattr(a.lib,name):
        fn=getattr(a.lib,name);fn.argtypes=[C.c_void_p,C.c_void_p]
        a.check(fn(C.byref(a.config),C.byref(a.tables)))
previous_kills=torch.zeros(8);previous_ticks=torch.zeros(8)
previous_floor=(a.obs[:,:81]==1).float().sum(1);wakes=torch.zeros(8)
uses=physical=0
torch.manual_seed(412)
for step in range(2100):
    assert torch.equal(a.obs,b.obs.cpu()) and torch.equal(a.mask,b.mask.cpu()),step
    action=a.heuristic().clone() if step%2 else torch.randint(0,9,(8,))
    if travel and step%3==0:action=torch.where(a.mask[:,9]>0,9,action)
    a.step(action);b.step(action.cuda())
    assert torch.equal(a.out,b.out.cpu()),(step,'CPU/CUDA output')
    out=a.out;ended=out[:,1]>0;dt=out[:,26] if travel else torch.ones(8)
    assert torch.equal(out[:,5]-previous_ticks,dt)
    assert torch.equal(a.obs[:,363],torch.where(ended,0,out[:,5]/limit))
    assert ((out[:,5]>=1)&(out[:,5]<=limit)).all()
    assert torch.equal(out[:,1],out[:,2]+out[:,6]+out[:,7])
    expected=out[:,3]-previous_kills+.002*(out[:,13]-previous_floor)-.001*dt+3*out[:,2]-out[:,6]
    assert torch.allclose(out[:,0],expected,atol=1e-5,rtol=0),(step,'reward')
    assert torch.equal(out[:,9]+out[:,10],24-out[:,3])
    assert torch.equal(out[:,14]+out[:,19],torch.full((8,),float(job['ogres'])))
    wakes+=out[:,21];assert ((wakes>=0)&(wakes<=job['ogres'])).all()
    assert (out[:,20]<=out[:,6]).all() and (out[:,22]<=out[:,23]).all()
    if travel:
        assert (out[:,32]==0).all();uses+=out[:,27].sum().item()
    physical+=dt.sum().item()
    wakes=torch.where(ended,0,wakes)
    previous_kills=torch.where(ended,0,out[:,3]).clone()
    previous_ticks=torch.where(ended,0,out[:,5]).clone()
    previous_floor=torch.where(ended,(a.obs[:,:81]==1).float().sum(1),out[:,13]).clone()
    if step%40==0:
        before=[x.clone() for x in [a.state,a.obs,a.mask,a.out]]
        a.step(action,active=torch.zeros(8,dtype=torch.bool))
        assert all(torch.equal(x,y) for x,y in zip(before,[a.state,a.obs,a.mask,a.out]))
if travel:assert uses>0 and physical>16800
print(json.dumps(dict(status='PASS',branch=branch.name,turn_limit=limit,ogres=job['ogres'],travel=travel,policy_transitions=16800,physical_turns=int(physical),travel_uses=int(uses))),flush=True)
