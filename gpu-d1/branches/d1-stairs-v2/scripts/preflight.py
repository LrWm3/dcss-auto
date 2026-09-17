import ctypes as C
import importlib.util
import pathlib
import sys
import torch
from assets import ASSETS
from common import ROOT,SOURCE,CORPUS,expand_weights,pad,env
from learn_env_ring_multi import Env
from symmetry import D4

torch.set_num_threads(1)
cpu=Env(8,24,seed=471,map_limit=2,device='cpu',corpus=CORPUS/'train',library_path=ASSETS/'stairs-clump0-test.so')
cpu.lib.stairs_semantic_test.argtypes=[C.c_void_p,C.c_void_p]
cpu.check(cpu.lib.stairs_semantic_test(C.byref(cpu.config),C.byref(cpu.tables)))
gpu=Env(8,24,seed=471,map_limit=2,corpus=CORPUS/'train',library_path=ASSETS/'stairs-clump0-test.so')
for step in range(512):
    assert torch.equal(cpu.obs,gpu.obs.cpu()),('observation',step)
    assert torch.equal(cpu.mask,gpu.mask.cpu()),('mask',step)
    a=cpu.heuristic().clone();cpu.step(a);gpu.step(a.cuda())
    assert torch.equal(cpu.out,gpu.out.cpu()),('outcome',step)
print('PASS native stairs semantics and 4,096 paired CPU/CUDA decisions',flush=True)

# New channels/actions cannot change old probabilities while masked/zeroed.
old_dir=ROOT/'branches/autoregressive-ordinary-v1/scripts'
spec=importlib.util.spec_from_file_location('old_symmetry',old_dir/'symmetry.py');sym=importlib.util.module_from_spec(spec);spec.loader.exec_module(sym)
spec=importlib.util.spec_from_file_location('old_model',old_dir/'tactical_models.py');oldmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(oldmod)
oldmod.D4=sym.D4
c=torch.load(SOURCE,map_location='cpu',weights_only=False)
old=oldmod.Policy('d4_exact',128).cuda();old.load_state_dict(c['model']);new=expand_weights(c['model'])
b=torch.load(ROOT/'learning-runs/autoregressive-anchor-buffer.pt',map_location='cuda',weights_only=False)
x,m=b['obs'][:128],b['mask'][:128];xx,mm=pad(x,m)
with torch.no_grad():
    a,v=old(x,m);z,w=new(xx,mm)
    torch.testing.assert_close(a.probs,z.probs[:,:18],atol=2e-6,rtol=2e-5)
    torch.testing.assert_close(v,w,atol=2e-6,rtol=2e-5)
    # Exact D4 covariance includes the new stair vector and route cue.
    xx[:,999:]=torch.randn_like(xx[:,999:]);mm[:,18]=1
    transform=D4('cuda');g=torch.full((len(xx),),1,device='cuda')
    order=torch.cat((transform.forward[1,:8],transform.forward[1,:8]+8,torch.tensor([16,17,18],device='cuda')))
    rotated_mask=torch.zeros_like(mm);rotated_mask[:,order]=mm
    p,v=new(xx,mm);q,w=new(transform.observation(xx,g),rotated_mask)
    torch.testing.assert_close(p.probs,q.probs[:,order],atol=2e-6,rtol=2e-5)
    torch.testing.assert_close(v,w,atol=2e-6,rtol=2e-5)
for split in ['train','validation','test']:
    e=env(split,1024,471)
    assert e.obs.shape==(1024,1015) and e.mask.shape==(1024,19)
    assert not e.obs[:,999:].any()
print('PASS checkpoint expansion, stair D4 covariance, and hidden initial stairs across all splits',flush=True)
