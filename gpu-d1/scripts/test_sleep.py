"""Parity and state checks for the original task with sleep as its only rule change."""
import ctypes as C
import torch
from learn_env_sleep import Env


class RNG(C.Structure):
    _fields_ = [('state', C.c_uint64), ('inc', C.c_uint64)]


class World(C.Structure):
    _fields_ = [('rng', RNG), ('hp', C.c_int), ('regen', C.c_int), ('blocks', C.c_int),
                ('fixture', C.c_int), ('episode', C.c_uint64), ('stats', C.c_uint64 * 13)]


class State(C.Structure):
    _fields_ = [('w', World), ('player', C.c_int), ('ticks', C.c_int), ('killed', C.c_int),
                ('pos', C.c_int16 * 8), ('energy', C.c_int16 * 8), ('occ', C.c_int16 * 5600),
                ('hp', C.c_int16 * 8), ('awake', C.c_int16 * 8)]


def main():
    torch.set_num_threads(1)
    cpu = Env(37, 8, seed=91, device='cpu')
    gpu = Env(37, 8, seed=91, device='cuda')
    assert torch.equal(cpu.obs, gpu.obs.cpu())
    states = C.cast(cpu.state.data_ptr(), C.POINTER(State))
    assert all(states[j].awake[i] == 0 for j in range(37) for i in range(8))
    woke = False
    for k in range(300):
        actions = cpu.heuristic().clone() if k % 2 == 0 else torch.randint(0, 9, (37,), dtype=torch.int64)
        cpu.step(actions)
        gpu.step(actions.cuda())
        assert torch.equal(cpu.obs, gpu.obs.cpu()), ('obs', k)
        assert torch.equal(cpu.mask, gpu.mask.cpu()), ('mask', k)
        assert torch.equal(cpu.out, gpu.out.cpu()), ('out', k)
        assert torch.equal(cpu.state, gpu.state.cpu()), ('state', k)
        woke |= any(states[j].awake[i] for j in range(37) for i in range(8) if states[j].hp[i] > 0)
    assert woke, 'no sleeping monster woke during the probe'
    print('PASS sleep: 37 worlds x 300 mixed actions, exact CPU/CUDA parity, asleep reset, wake transition')


if __name__ == '__main__':
    main()
