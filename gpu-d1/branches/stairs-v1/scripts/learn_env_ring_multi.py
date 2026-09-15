"""Multi-layout version of the corrected 40-enemy remembered-ring task."""
import ctypes as C
import pathlib
import numpy as np
import torch

from learn_env import ROOT, load_map
from learn_env_v2 import read_maps


class Tables(C.Structure):
    _fields_ = [
        ('floor', C.c_void_p), ('cells', C.c_void_p), ('index', C.c_void_p),
        ('distance', C.c_void_p), ('ncells', C.c_int),
        ('map_ncells', C.c_void_p), ('distance_offsets', C.c_void_p),
        ('n_maps', C.c_int), ('map_filter', C.c_int),
    ]


_LIB = None
_LIBRARIES = {}


def library(path=None):
    global _LIB
    if path is not None:
        path = str(pathlib.Path(path).resolve())
        if path not in _LIBRARIES:
            lib = C.CDLL(path)
            p, i = C.c_void_p, C.c_int
            lib.learn_init.argtypes = [p, i, p, p, C.c_uint64, p, p, p, i]
            lib.learn_step.argtypes = [p, i, p, p, p, i, p, p, p, p, i]
            lib.learn_heuristic.argtypes = [p, i, p, p, p, p, i]
            _LIBRARIES[path] = lib
        return _LIBRARIES[path]
    if _LIB is None:
        _LIB = C.CDLL(str(ROOT / 'build/learn_sleep_explore_ring_walls_multi.so'))
        p, i = C.c_void_p, C.c_int
        _LIB.learn_init.argtypes = [p, i, p, p, C.c_uint64, p, p, p, i]
        _LIB.learn_step.argtypes = [p, i, p, p, p, i, p, p, p, p, i]
        _LIB.learn_heuristic.argtypes = [p, i, p, p, p, p, i]
    return _LIB


class Env:
    def __init__(self, batch=512, enemies=40, seed=0, device='cuda', limit=1024,
                 corpus=ROOT / 'fixtures/d1-corpus-388/train', map_filter=-1,
                 map_limit=None, library_path=None):
        if not 1 <= enemies <= 40 or limit != 1024:
            raise ValueError('This task uses 1..40 enemies and a 1024-decision deadline')
        self.device = torch.device('cuda:0' if device == 'cuda' else device)
        self.batch, self.enemies, self.limit = batch, enemies, limit
        self.lib = library(library_path)
        if hasattr(self.lib, 'learn_step_active'):
            p, i = C.c_void_p, C.c_int
            self.lib.learn_step_active.argtypes = [p, i, p, p, p, i, p, p, p, p, p, i]
        raw_arrays, self.metadata = read_maps(corpus, map_limit=map_limit)
        floors = np.concatenate([a[0] for a in raw_arrays])
        cells = np.concatenate([a[1] for a in raw_arrays])
        indices = np.concatenate([a[2] for a in raw_arrays])
        distances = np.concatenate([a[3] for a in raw_arrays])
        ncells = np.asarray([m['cells'] for m in self.metadata], dtype=np.int32)
        offsets = np.concatenate(([0], np.cumsum(ncells[:-1], dtype=np.int64))).astype(np.int32)
        self.arrays = [torch.from_numpy(a.view(np.int16) if a.dtype == np.uint16 else a).to(self.device)
                       for a in (floors, cells, indices, distances, ncells, offsets)]
        self.tables = Tables(
            self.arrays[0].data_ptr(), self.arrays[1].data_ptr(), self.arrays[2].data_ptr(),
            self.arrays[3].data_ptr(), int(ncells[0]), self.arrays[4].data_ptr(),
            self.arrays[5].data_ptr(), len(self.metadata), map_filter)

        header, kinds, _ = load_map()
        ac = header[2] // 100
        gdr = [int((65536 * (ac + j)) ** 0.25) for j in range(2)]
        values = [enemies, *header[:7], 1, *gdr, *kinds]
        self.config = (C.c_int * len(values))(*values)
        assert C.sizeof(self.config) == self.lib.learn_config_bytes()
        self.state = torch.empty((batch, self.lib.learn_state_bytes()), dtype=torch.uint8, device=self.device)
        self.obs = torch.empty((batch, self.lib.learn_obs_size()), device=self.device)
        self.action_size = self.lib.learn_action_size() if hasattr(self.lib, 'learn_action_size') else 9
        self.out_size = self.lib.learn_out_size() if hasattr(self.lib, 'learn_out_size') else 8
        self.mask = torch.empty((batch, self.action_size), device=self.device)
        self.out = torch.empty((batch, self.out_size), device=self.device)
        self.actions = torch.empty(batch, dtype=torch.int64, device=self.device)
        self.reset(seed)

    @property
    def stream(self):
        return torch.cuda.current_stream(self.device).cuda_stream if self.device.type == 'cuda' else 0

    def check(self, code):
        if code:
            raise RuntimeError(f'multi-map ring task call failed with error {code}')

    def reset(self, seed):
        self.check(self.lib.learn_init(self.state.data_ptr(), self.batch, C.byref(self.config),
                   C.byref(self.tables), seed, self.obs.data_ptr(), self.mask.data_ptr(),
                   self.stream, self.device.type == 'cuda'))
        return self.obs

    def step(self, actions, active=None):
        assert actions.device == self.device and actions.dtype == torch.int64 and actions.is_contiguous()
        if active is not None and hasattr(self.lib, 'learn_step_active'):
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
