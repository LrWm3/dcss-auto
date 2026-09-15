"""LOS/knowledge leak checks, ogre dynamics, and CPU/CUDA parity."""
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
    assert cpu.obs.shape[1]==502 and cpu.action_size==9
    cpu.lib.learn_semantic_test.argtypes=[C.c_void_p,C.c_void_p]
    cpu.check(cpu.lib.learn_semantic_test(C.byref(cpu.config),C.byref(cpu.tables)))
    cpu.lib.learn_ogre_test.argtypes=[C.c_void_p,C.c_void_p]
    cpu.check(cpu.lib.learn_ogre_test(C.byref(cpu.config),C.byref(cpu.tables)))
    previous_kills=torch.zeros(8)
    wakes=torch.zeros(8)
    previous_floor=(cpu.obs[:,:81]==1).float().sum(1)
    torch.manual_seed(412)
    for step in range(1050):
        assert torch.equal(cpu.obs,gpu.obs.cpu()),(job['id'],step,'obs')
        assert torch.equal(cpu.mask,gpu.mask.cpu()),(job['id'],step,'mask')
        if ji==0:
            action=cpu.heuristic().clone() if step%2 else torch.randint(0,9,(8,))
            reference_actions.append(action)
        else: action=reference_actions[step]
        cpu.step(action);gpu.step(action.cuda())
        assert torch.equal(cpu.out,gpu.out.cpu()),(job['id'],step,'out')
        if ji==0:reference_out.append(cpu.out[:,1:8].clone())
        # Wake rules intentionally alter combat across arms.
        out=cpu.out
        expected_reward=(out[:,3]-previous_kills)+.002*(out[:,13]-previous_floor)-.001+3*out[:,2]-out[:,6]
        assert torch.allclose(out[:,0],expected_reward,atol=2e-6,rtol=0), 'Exploration/terminal reward mismatch'
        ended=out[:,1]>0
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
    print(job['id'],'PASS: native occlusion/knowledge-leak assertions; 8,400 CPU/CUDA world steps; ogre dynamics/diagnostics; visibility-based reward accounting; active masking',flush=True)

# Integrating optional ogres must leave the zero-ogre task unchanged.
reference_suite=ROOT.parents[1]/'learning-runs/vision24-512-los-awareness-30m'
reference_lib=next((reference_suite/'build').glob('*.so'))
zero_job=next(j for j in jobs if j['ogres']==0 and j['monster_wake_los'])
args=dict(batch=8,enemies=24,seed=771,map_limit=2,limit=512,device='cpu',
          corpus=ROOT.parents[1]/'fixtures/d1-corpus-388/train')
a=Env(library_path=reference_lib,**args)
b=Env(library_path=suite/'build'/(library_key(zero_job)+'.so'),**args)
torch.manual_seed(19)
for step in range(1050):
    assert torch.equal(a.obs,b.obs) and torch.equal(a.mask,b.mask), ('zero-ogre obs',step)
    action=a.heuristic().clone() if step%2 else torch.randint(0,9,(8,))
    a.step(action);b.step(action)
    assert torch.equal(a.out,b.out[:,:14]), ('zero-ogre dynamics',step)
print('PASS: zero-ogre integration exactly matches original LOS-wake task for 8,400 world steps',flush=True)
