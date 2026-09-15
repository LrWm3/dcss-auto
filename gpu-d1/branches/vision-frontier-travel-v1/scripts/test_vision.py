"""LOS/knowledge leak checks, ogre dynamics, and CPU/CUDA parity."""
import resource
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
import ctypes as C
import json
import pathlib
import sys
import torch
from learn_env_ring_multi import Env
from run_ring_ablations import ROOT, library_key

torch.set_num_threads(1)
suite=pathlib.Path(sys.argv[1]); jobs=json.loads((suite/'manifest.json').read_text())['jobs']
reference_actions=[]; reference_out=[]
for ji,job in enumerate(jobs):
    args=dict(batch=8,enemies=job['enemies'],seed=137,map_limit=2,limit=512,
              corpus=ROOT.parents[1]/'fixtures/d1-corpus-388/train',
              library_path=suite/'build'/(library_key(job)+'.so'))
    cpu,gpu=Env(device='cpu',**args),Env(device='cuda',**args)
    assert cpu.obs.shape[1]==502 and cpu.action_size==10
    cpu.lib.learn_semantic_test.argtypes=[C.c_void_p,C.c_void_p]
    cpu.check(cpu.lib.learn_semantic_test(C.byref(cpu.config),C.byref(cpu.tables)))
    cpu.lib.learn_ogre_test.argtypes=[C.c_void_p,C.c_void_p]
    cpu.check(cpu.lib.learn_ogre_test(C.byref(cpu.config),C.byref(cpu.tables)))
    cpu.lib.learn_travel_test.argtypes=[C.c_void_p,C.c_void_p]
    cpu.check(cpu.lib.learn_travel_test(C.byref(cpu.config),C.byref(cpu.tables)))
    previous_ticks=torch.zeros(8)
    macro_turns=macro_uses=0
    previous_kills=torch.zeros(8)
    wakes=torch.zeros(8)
    previous_floor=(cpu.obs[:,:81]==1).float().sum(1)
    torch.manual_seed(412)
    for step in range(1050):
        assert torch.equal(cpu.obs,gpu.obs.cpu()),(job['id'],step,'obs')
        assert torch.equal(cpu.mask,gpu.mask.cpu()),(job['id'],step,'mask')
        action=cpu.heuristic().clone() if step%2 else torch.randint(0,9,(8,))
        if step%3==0: action=torch.where(cpu.mask[:,9]>0,9,action)
        cpu.step(action);gpu.step(action.cuda())
        assert torch.equal(cpu.out,gpu.out.cpu()),(job['id'],step,'out')
        if ji==0:reference_out.append(cpu.out[:,1:8].clone())
        # Wake rules intentionally alter combat across arms.
        out=cpu.out
        expected_reward=(out[:,3]-previous_kills)+.002*(out[:,13]-previous_floor)-.001*out[:,26]+3*out[:,2]-out[:,6]
        assert torch.allclose(out[:,0],expected_reward,atol=1e-5,rtol=0), 'Exploration/terminal reward mismatch'
        ended=out[:,1]>0
        assert torch.equal(out[:,5]-previous_ticks,out[:,26])
        previous_ticks=torch.where(ended,0,out[:,5]).clone()
        macro_turns+=out[:,28].sum().item();macro_uses+=out[:,27].sum().item()
        assert ((out[:,26]>=1)&(out[:,26]<=512)).all()
        assert (out[:,32]==0).all()

        wakes+=out[:,21]
        assert ((wakes>=0)&(wakes<=job['ogres'])).all()
        assert torch.equal(out[:,14]+out[:,19],torch.full((8,),float(job['ogres'])))
        assert (out[:,20]<=out[:,6]).all()
        assert (out[:,22]<=out[:,23]).all()
        assert (out[:,18]<=out[:,19]).all()
        assert (out[:,24]<=job['ogres']).all()
        assert (out[:,25]<=out[:,19]).all()
        wakes=torch.where(ended,0,wakes)
        previous_kills=torch.where(ended,0,out[:,3]).clone()
        previous_floor=torch.where(ended,(cpu.obs[:,:81]==1).float().sum(1),out[:,13]).clone()
        assert torch.equal(out[:,1],out[:,2]+out[:,6]+out[:,7])
        assert ((out[:,5]>=1)&(out[:,5]<=512)).all()
        assert torch.equal(out[:,9]+out[:,10],24-out[:,3])
        assert ((out[:,8]>=out[:,3])&(out[:,8]<=24)).all()
        assert ((out[:,11]>=0)&(out[:,11]<=1)).all()
        if step%40==0:
            active=torch.zeros(8,dtype=torch.bool)
            saved=(cpu.state.clone(),cpu.obs.clone(),cpu.mask.clone(),cpu.out.clone())
            cpu.step(action,active=active)
            assert all(torch.equal(a,b) for a,b in zip(saved,(cpu.state,cpu.obs,cpu.mask,cpu.out)))
    assert macro_uses>0 and macro_turns>macro_uses
    print(job['id'],f'{macro_uses} trips / {macro_turns} travel turns; PASS: native occlusion/knowledge-leak assertions; 8,400 CPU/CUDA world steps; ogre dynamics/diagnostics; visibility-based reward accounting; active masking',flush=True)

# Primitive-only replay must match the original ogre task exactly.
reference_suite=ROOT.parents[1]/'learning-runs/vision-ogre2-wake-screen-30m'
reference_lib=next((reference_suite/'build').glob('*wake1-ogres2*.so'))
job=next(j for j in jobs if j['ogres']==2 and j['monster_wake_los'])
args=dict(batch=8,enemies=26,seed=771,map_limit=2,limit=512,device='cpu',
          corpus=ROOT.parents[1]/'fixtures/d1-corpus-388/train')
a=Env(library_path=reference_lib,**args)
b=Env(library_path=suite/'build'/(library_key(job)+'.so'),**args)
torch.manual_seed(19)
for step in range(1050):
    assert torch.equal(a.obs,b.obs) and torch.equal(a.mask,b.mask[:,:9]), ('primitive obs',step)
    action=a.heuristic().clone() if step%2 else torch.randint(0,9,(8,))
    a.step(action);b.step(action)
    assert torch.equal(a.out,b.out[:,:26]), ('primitive dynamics',step)
print('PASS: primitive-only replay exactly matches original ogre task for 8,400 turns',flush=True)
