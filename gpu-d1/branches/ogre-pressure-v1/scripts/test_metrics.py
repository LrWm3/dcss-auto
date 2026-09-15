"""Instrumentation must preserve old transitions and agree on CPU/CUDA."""
import pathlib, sys, torch
from learn_env_ring_multi import Env
root=pathlib.Path(__file__).resolve().parents[3]
lib=pathlib.Path(sys.argv[1])
old=root/'learning-runs/ogre2-baseline-30m/build/ring-reward2-frontier1-route1-ogres2-features0.so'
args=dict(batch=8,enemies=26,seed=123,map_limit=2,corpus=root/'fixtures/d1-corpus-388/train')
a=Env(library_path=old,device='cpu',**args)
b=Env(library_path=lib,device='cpu',**args)
c=Env(library_path=lib,device='cuda',**args)
for step in range(1050):
    action=a.heuristic().clone()
    a.step(action);b.step(action);c.step(action.cuda())
    assert torch.equal(a.obs,b.obs) and torch.equal(b.obs,c.obs.cpu())
    assert torch.equal(a.mask,b.mask) and torch.equal(b.mask,c.mask.cpu())
    assert torch.equal(a.out,b.out[:,:15]) and torch.equal(b.out,c.out.cpu())
    assert ((b.out[:,15]>=0)&(b.out[:,15]<=2)).all()
    assert ((b.out[:,16]>=0)&(b.out[:,16]<=b.out[:,17])&(b.out[:,17]<=1)).all()
print('PASS: original dynamics/observations preserved; new counters match CPU/CUDA over 8400 world turns')
