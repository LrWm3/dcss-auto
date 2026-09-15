"""CPU/CUDA parity and matched initial ordinary encounters across ogre counts."""
import pathlib
import sys
import torch
from learn_env_ring_multi import Env

suite=pathlib.Path(sys.argv[1]); corpus=pathlib.Path(__file__).resolve().parents[3]/'fixtures/d1-corpus-388/train'
initial=[]
for n,feature in [(0,0),(1,7),(2,7)]:
    lib=suite/'build'/f'ring-reward2-frontier1-route1-fast-ogres{n}-features{feature}.so'
    if not lib.exists():
        lib=suite/'build'/f'ring-reward2-frontier1-route1-ogres{n}-features{feature}.so'
    args=dict(batch=8,enemies=24+n,seed=123,map_limit=2,corpus=corpus,library_path=lib)
    cpu=Env(device='cpu',**args); gpu=Env(device='cuda',**args)
    initial.append(cpu.obs.clone())
    assert (cpu.obs[:,421:421+24*8:8]==1).all()
    for i in range(24,24+n):
        delta=cpu.obs[:,162+i*5:164+i*5]*torch.tensor([80.,70.])
        assert (delta.abs().max(1).values>=11.999).all()
        assert (cpu.obs[:,421+i*8]==0).all()
    for step in range(1050):
        assert torch.equal(cpu.obs,gpu.obs.cpu()), (n,step,'obs')
        assert torch.equal(cpu.mask,gpu.mask.cpu()), (n,step,'mask')
        action=cpu.heuristic().clone()
        _,a=cpu.step(action); _,b=gpu.step(action.cuda())
        assert torch.equal(a,b.cpu()),(n,step,'out')
    del cpu,gpu
for obs in initial[1:]:
    assert torch.equal(initial[0][:,162:282],obs[:,162:282]) # 24 ordinary records.
    assert torch.equal(initial[0][:,362:366],obs[:,362:366]) # Player state.
print('PASS: CPU/CUDA trajectories for N=0/1/2, spawn distance, role bits, matched regular/player placements')
