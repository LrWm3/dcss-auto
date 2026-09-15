"""Resident CUDA task with a CPU reference using identical transition rules."""
import collections
import ctypes as C
import pathlib
import struct
import numpy as np
import torch

ROOT = pathlib.Path(__file__).resolve().parents[1]

class Tables(C.Structure):
    _fields_ = [(k, C.c_void_p) for k in ('floor', 'cells', 'index', 'distance')] + [('ncells', C.c_int)]


def load_map():
    raw = (ROOT / 'fixtures/fixture.bin').read_bytes()
    assert struct.unpack_from('<I', raw)[0] == 0x44314750
    header = struct.unpack_from('<8i', raw, 4)
    kinds = struct.unpack_from('<24i', raw, 36)
    floor = np.frombuffer(raw, np.uint8, count=5600, offset=132).copy()
    native_dist = np.frombuffer(raw, '<u2', count=5600, offset=5732)
    cells = np.flatnonzero((floor != 0) & (native_dist < 65535)).astype(np.int16)
    index = np.full(5600, -1, np.int16)
    index[cells] = np.arange(len(cells))
    neighbors = {}
    for p in cells:
        p = int(p); x, y = p % 80, p // 80
        neighbors[p] = [(y+dy)*80+x+dx for dx, dy in
                        ((0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1))
                        if 0 <= x+dx < 80 and 0 <= y+dy < 70 and floor[(y+dy)*80+x+dx]]
    distance = np.full((len(cells), 5600), 65535, np.uint16)
    for i, source in enumerate(cells):
        ds = distance[i]; ds[source] = 0
        queue = collections.deque([int(source)])
        while queue:
            p = queue.popleft(); nd = int(ds[p])+1
            for q in neighbors[p]:
                if ds[q] == 65535:
                    ds[q] = nd; queue.append(q)
    return header, kinds, (floor, cells, index, distance)

_MAP = None
_LIB = None

def library():
    global _LIB
    if _LIB is None:
        _LIB = C.CDLL(str(ROOT / 'build/learn.so'))
        p, i = C.c_void_p, C.c_int
        _LIB.learn_init.argtypes = [p,i,p,p,C.c_uint64,p,p,p,i]
        _LIB.learn_step.argtypes = [p,i,p,p,p,i,p,p,p,p,i]
        _LIB.learn_heuristic.argtypes = [p,i,p,p,p,p,i]
        _LIB.learn_semantic_test.argtypes = [p,p]
    return _LIB

class Env:
    def __init__(self, batch=512, enemies=6, seed=0, device='cuda', limit=256):
        global _MAP
        if not 1 <= enemies <= 8 or limit != 256:
            raise ValueError('Supported: 1..8 enemies, fixed 256-decision deadline')
        if _MAP is None:
            _MAP = load_map()
        header, kinds, arrays = _MAP
        self.device = torch.device('cuda:0' if device == 'cuda' else device)
        self.batch, self.enemies, self.limit = batch, enemies, limit
        self.lib = library()
        ac = header[2] // 100
        gdr = [int((65536 * (ac+j)) ** 0.25) for j in range(2)]
        values = [enemies, *header[:7], 1, *gdr, *kinds]
        self.config = (C.c_int * len(values))(*values)
        assert C.sizeof(self.config) == self.lib.learn_config_bytes()
        # int16 backing storage preserves unsigned distance bits (65535 sentinel).
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
            raise RuntimeError(f'CUDA task call failed with error {code}')

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
                   C.byref(self.tables), self.actions.data_ptr(), self.stream, self.device.type == 'cuda'))
        return self.actions
