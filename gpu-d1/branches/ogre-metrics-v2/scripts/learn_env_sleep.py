"""The original fixed-map environment with only the sleep rule enabled."""
import ctypes as C
import numpy as np
import torch
from learn_env import ROOT, Tables, load_map

_LIB = None
LIB_NAME = 'learn_sleep.so'


def library():
    global _LIB
    if _LIB is None:
        _LIB = C.CDLL(str(ROOT / 'build' / LIB_NAME))
        p, i = C.c_void_p, C.c_int
        _LIB.learn_init.argtypes = [p, i, p, p, C.c_uint64, p, p, p, i]
        _LIB.learn_step.argtypes = [p, i, p, p, p, i, p, p, p, p, i]
        _LIB.learn_heuristic.argtypes = [p, i, p, p, p, p, i]
    return _LIB


class Env:
    def __init__(self, batch=512, enemies=6, seed=0, device='cuda', limit=256):
        if not 1 <= enemies <= 40 or limit < 1:
            raise ValueError('Supported: 1..40 enemies, positive decision deadline')
        header, kinds, arrays = load_map()
        self.device = torch.device('cuda:0' if device == 'cuda' else device)
        self.batch, self.enemies, self.limit = batch, enemies, limit
        self.lib = library()
        ac = header[2] // 100
        gdr = [int((65536 * (ac + j)) ** 0.25) for j in range(2)]
        values = [enemies, *header[:7], 1, *gdr, *kinds]
        self.config = (C.c_int * len(values))(*values)
        self.arrays = [torch.from_numpy(a.view(np.int16) if a.dtype == np.uint16 else a).to(self.device)
                       for a in arrays]
        self.tables = Tables(*(a.data_ptr() for a in self.arrays), len(arrays[1]))
        self.state = torch.empty((batch, self.lib.learn_state_bytes()), dtype=torch.uint8, device=self.device)
        self.obs = torch.empty((batch, self.lib.learn_obs_size()), device=self.device)
        self.mask = torch.empty((batch, 9), device=self.device)
        self.out = torch.empty((batch, 8), device=self.device)
        self.actions = torch.empty(batch, dtype=torch.int64, device=self.device)
        self.reset(seed)

    @property
    def stream(self):
        return torch.cuda.current_stream(self.device).cuda_stream if self.device.type == 'cuda' else 0

    def check(self, code):
        if code:
            raise RuntimeError(f'CUDA sleep task call failed with error {code}')

    def reset(self, seed):
        self.check(self.lib.learn_init(self.state.data_ptr(), self.batch, C.byref(self.config),
                   C.byref(self.tables), seed, self.obs.data_ptr(), self.mask.data_ptr(),
                   self.stream, self.device.type == 'cuda'))
        return self.obs

    def step(self, actions, active=None):
        assert actions.device == self.device and actions.dtype == torch.int64 and actions.is_contiguous()
        if active is not None and hasattr(self.lib, 'learn_step_active'):
            p, i = C.c_void_p, C.c_int
            self.lib.learn_step_active.argtypes = [p, i, p, p, p, i, p, p, p, p, p, i]
            assert active.device == self.device and active.dtype == torch.bool and active.is_contiguous()
            assert active.shape == (self.batch,)
            self.check(self.lib.learn_step_active(self.state.data_ptr(), self.batch, C.byref(self.config),
                       C.byref(self.tables), actions.data_ptr(), self.limit, self.obs.data_ptr(),
                       self.mask.data_ptr(), self.out.data_ptr(), active.data_ptr(), self.stream,
                       self.device.type == 'cuda'))
            return self.obs, self.out
        self.check(self.lib.learn_step(self.state.data_ptr(), self.batch, C.byref(self.config),
                   C.byref(self.tables), actions.data_ptr(), self.limit, self.obs.data_ptr(),
                   self.mask.data_ptr(), self.out.data_ptr(), self.stream, self.device.type == 'cuda'))
        return self.obs, self.out

    def heuristic(self):
        self.check(self.lib.learn_heuristic(self.state.data_ptr(), self.batch, C.byref(self.config),
                   C.byref(self.tables), self.actions.data_ptr(), self.stream,
                   self.device.type == 'cuda'))
        return self.actions
