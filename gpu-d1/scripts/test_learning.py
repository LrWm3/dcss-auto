"""Behavior, determinism and stream tests for the actual RL environment."""
import ctypes as C
import torch
import numpy as np
from learn_env import Env


class RNG(C.Structure):
    _fields_=[('state',C.c_uint64),('inc',C.c_uint64)]

class World(C.Structure):
    _fields_=[('rng',RNG),('hp',C.c_int),('regen',C.c_int),('blocks',C.c_int),
              ('fixture',C.c_int),('episode',C.c_uint64),('stats',C.c_uint64*13)]

class State(C.Structure):
    _fields_=[('w',World),('player',C.c_int),('ticks',C.c_int),('killed',C.c_int),
              ('pos',C.c_int16*8),('energy',C.c_int16*8),('occ',C.c_int16*5600),('hp',C.c_int16*8)]

def invariants(env):
    assert C.sizeof(State)==env.state.shape[1]
    states=C.cast(env.state.data_ptr(),C.POINTER(State))
    floor=env.arrays[0].numpy()
    for j in range(env.batch):
        s=states[j]
        occ=np.ctypeslib.as_array(s.occ)
        live=[i for i in range(env.enemies) if s.hp[i]>0]
        assert s.killed==env.enemies-len(live)
        assert 0<s.w.hp<=18 and 0<=s.w.regen<100 and 0<=s.ticks<256
        assert floor[s.player] and occ[s.player]==-1
        assert np.count_nonzero(occ>=0)==len(live)
        assert len(set(s.pos[i] for i in live))==len(live)
        for i in range(env.enemies):
            if i in live:
                assert floor[s.pos[i]] and occ[s.pos[i]]==i and s.energy[i]<80
            else:
                assert s.energy[i]==-30000

def main():
    torch.set_num_threads(1)
    torch.manual_seed(137)
    for enemies in (1,6,8):
        cpu = Env(37, enemies, seed=91, device='cpu')
        gpu = Env(37, enemies, seed=91)
        cpu.check(cpu.lib.learn_semantic_test(C.byref(cpu.config), C.byref(cpu.tables)))
        assert torch.equal(cpu.obs, gpu.obs.cpu())
        totals = torch.zeros(8)
        for k in range(300):
            actions = torch.randint(0,9,(37,)) if k % 2 else cpu.heuristic().clone()
            cpu.step(actions); gpu.step(actions.cuda())
            assert torch.equal(cpu.obs, gpu.obs.cpu()), (enemies,k,'observation')
            assert torch.equal(cpu.mask, gpu.mask.cpu()), (enemies,k,'mask')
            assert torch.equal(cpu.out, gpu.out.cpu()), (enemies,k,'outcome')
            assert torch.equal(cpu.state, gpu.state.cpu()), (enemies,k,'full state')
            o = cpu.out
            assert torch.equal(o[:,1], o[:,2]+o[:,6]+o[:,7])
            assert ((o[:,3]>=0) & (o[:,3]<=enemies)).all()
            assert ((o[:,4]>=0) & (o[:,4]<=18)).all()
            totals += (o * o[:,1:2]).sum(0)
            if k%25==0: invariants(cpu)
        assert totals[1]>0 and totals[2]>0
        print(f'PASS enemies={enemies}: 37 worlds x 300 mixed actions, exact full-state CPU/CUDA parity; {int(totals[1])} terminations')
    # Custom kernels must honor the stream that produces actions and consumes observations.
    with torch.cuda.stream(torch.cuda.Stream()):
        a=Env(37,6,seed=91)
        a.step(torch.full((37,),8,dtype=torch.int64,device='cuda'))
        got=a.obs.clone()
    torch.cuda.synchronize()
    b=Env(37,6,seed=91,device='cpu'); b.step(torch.full((37,),8,dtype=torch.int64))
    assert torch.equal(got.cpu(),b.obs)
    print('PASS non-default CUDA stream, movement, last kill/no retaliation, timeout, death, reset, occupancy/dead-actor invariants')

if __name__ == '__main__': main()
