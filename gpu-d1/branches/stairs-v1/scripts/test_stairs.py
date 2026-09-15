"""Reward/termination semantics, CPU/CUDA parity, and matched four-arm dynamics."""
import ctypes as C
import json
import pathlib
import sys
import torch
from learn_env_ring_multi import Env
from run_ring_ablations import library_key, ROOT

torch.set_num_threads(1)
suite = pathlib.Path(sys.argv[1])
jobs = json.loads((suite/'manifest.json').read_text())['jobs']
reference = None
for job in jobs:
    args = dict(batch=8, enemies=26, seed=137, map_limit=2,
                corpus=ROOT.parents[1]/'fixtures/d1-corpus-388/train',
                library_path=suite/'build'/(library_key(job)+'.so'))
    cpu, gpu = Env(device='cpu', **args), Env(device='cuda', **args)
    assert cpu.obs.shape[1] == 752 and cpu.mask.shape[1] == 10
    cpu.lib.learn_semantic_test.argtypes = [C.c_void_p, C.c_void_p]
    cpu.check(cpu.lib.learn_semantic_test(C.byref(cpu.config), C.byref(cpu.tables)))
    assert (cpu.mask[:,9]==1).all()
    assert (cpu.obs[:,741:750:3]==1).all()
    assert (cpu.obs[:,421:741:8]==0).all()
    snapshots = []
    torch.manual_seed(412)
    for step in range(1050):
        assert torch.equal(cpu.obs, gpu.obs.cpu()), (job['id'],step,'obs')
        assert torch.equal(cpu.mask, gpu.mask.cpu())
        actions = cpu.heuristic().clone() if step%2 else torch.randint(0,10,(8,))
        cpu.step(actions); gpu.step(actions.cuda())
        assert torch.equal(cpu.out, gpu.out.cpu()), (job['id'],step,'out')
        assert torch.equal(cpu.out[:,1], cpu.out[:,2]+cpu.out[:,6]+cpu.out[:,7])
        if step%50==0:
            snapshots.append(cpu.state.clone())
    if reference is None:
        reference=snapshots
    else:
        assert all(torch.equal(a,b) for a,b in zip(reference,snapshots)), 'Reward arms changed matched dynamics'
    print(job['id'], 'PASS: native semantics, 8,400 CPU/CUDA world steps, matched dynamics', flush=True)
