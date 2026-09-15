"""GPU-resident multi-map sleep/statistics task."""
import ctypes as C
import pathlib
import struct
import numpy as np
import torch

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAGIC = 0x44325650


class Tables(C.Structure):
    _fields_ = [
        ('floor', C.c_void_p),
        ('cells', C.c_void_p),
        ('index', C.c_void_p),
        ('distance', C.c_void_p),
        ('los', C.c_void_p),
        ('ncells', C.c_void_p),
        ('distance_offsets', C.c_void_p),
        ('n_maps', C.c_int),
    ]


def read_maps(root, map_limit=None):
    def map_key(path):
        try:
            return int(path.stem.split('-', 1)[1])
        except (IndexError, ValueError):
            return path.name

    root = pathlib.Path(root)
    paths = sorted(root.glob('map-*.bin'), key=map_key)
    # Accept either a split directory or the corpus root produced by the
    # collector (`.../d1-corpus-388/all`).
    if not paths and (root / 'all').is_dir():
        root = root / 'all'
        paths = sorted(root.glob('map-*.bin'), key=map_key)
    if map_limit is not None:
        if not 1 <= map_limit <= len(paths):
            raise ValueError(f'map_limit must be 1..{len(paths)}')
        # Nested, seed-independent subsets, retaining the original map first.
        # Select before reading so small ablations do not load the full corpus.
        import hashlib
        paths = paths[:1] + sorted(paths[1:], key=lambda p: hashlib.sha256(p.name.encode()).digest())
        paths = sorted(paths[:map_limit], key=map_key)
    arrays, metadata = [], []
    for path in paths:
        raw = path.read_bytes()
        magic, seed, ncells = struct.unpack_from('<3I', raw)
        if magic != MAGIC or ncells > 5600:
            raise ValueError(f'bad corpus map: {path}')
        hp, ac, ev, sh = struct.unpack_from('<4i', raw, 12)
        off = 28
        floor = np.frombuffer(raw, np.uint8, 5600, off).copy(); off += 5600
        cells = np.frombuffer(raw, '<i2', 5600, off).copy(); off += 11200
        index = np.frombuffer(raw, '<i2', 5600, off).copy(); off += 11200
        distance = np.frombuffer(raw, '<u2', ncells * 5600, off).copy(); off += ncells * 11200
        los = np.frombuffer(raw, '<u4', 5600 * 10, off).copy()
        arrays.append((floor, cells, index, distance, los))
        metadata.append(dict(path=path.name, seed=seed, cells=ncells, hp=hp, ac=ac, ev=ev, sh=sh))
    if not arrays:
        raise ValueError('corpus must contain at least one map')
    return arrays, metadata


_LIB = None


def library():
    global _LIB
    if _LIB is None:
        _LIB = C.CDLL(str(ROOT / 'build/learn_v2.so'))
        p, i = C.c_void_p, C.c_int
        _LIB.learn_v2_init.argtypes = [p, i, p, p, C.c_uint64, p, p, p, i]
        _LIB.learn_v2_step.argtypes = [p, i, p, p, p, i, p, p, p, p, i]
        _LIB.learn_v2_heuristic.argtypes = [p, i, p, p, p, p, i]
    return _LIB


class EnvV2:
    def __init__(self, batch=512, enemies=8, seed=0, device='cuda', limit=512,
                 corpus=ROOT / 'fixtures/v2-corpus', sleep_radius=6, stat_mode=1, player_mode=1):
        if not 1 <= enemies <= 8:
            raise ValueError('enemies must be 1..8')
        self.device = torch.device('cuda:0' if device == 'cuda' else device)
        self.batch, self.enemies, self.limit = batch, enemies, limit
        self.lib = library()
        raw_arrays, self.metadata = read_maps(corpus)
        # Flatten fixed-width map tables so the CUDA kernel receives a small
        # descriptor instead of a pointer array whose size grows with the
        # corpus. Distance rows are variable-width, so offsets are in rows of
        # 5600 cells.
        floors = np.concatenate([row[0] for row in raw_arrays])
        cells = np.concatenate([row[1] for row in raw_arrays])
        indices = np.concatenate([row[2] for row in raw_arrays])
        distances = np.concatenate([row[3] for row in raw_arrays])
        losses = np.concatenate([row[4] for row in raw_arrays])
        ncells = np.asarray([m['cells'] for m in self.metadata], dtype=np.int32)
        distance_offsets = np.concatenate(([0], np.cumsum(ncells[:-1], dtype=np.int64))).astype(np.int32)
        self.arrays = [torch.from_numpy(a.view(np.int16) if a.dtype == np.uint16 else a).to(self.device)
                       for a in (floors, cells, indices, distances, losses, ncells, distance_offsets)]
        self.tables = Tables(*(C.c_void_p(a.data_ptr()) for a in self.arrays), len(raw_arrays))
        # Deliberately robust proxy player: this leaves room to learn engagement
        # without making the strong/slow archetype an almost-certain death.
        self.config = (C.c_int * 8)(enemies, sleep_radius, stat_mode, player_mode, 30, 1, 8, 90)
        assert C.sizeof(self.config) == self.lib.learn_v2_config_bytes()
        self.state = torch.empty((batch, self.lib.learn_v2_state_bytes()), dtype=torch.uint8, device=self.device)
        self.obs = torch.empty((batch, self.lib.learn_v2_obs_size()), device=self.device)
        self.mask = torch.empty((batch, 9), device=self.device)
        self.out = torch.empty((batch, self.lib.learn_v2_out_size()), device=self.device)
        self.actions = torch.empty(batch, dtype=torch.int64, device=self.device)
        self.reset(seed)

    @property
    def stream(self):
        return torch.cuda.current_stream(self.device).cuda_stream if self.device.type == 'cuda' else 0

    def check(self, code):
        if code:
            raise RuntimeError(f'v2 task call failed: {code}')

    def reset(self, seed):
        self.check(self.lib.learn_v2_init(self.state.data_ptr(), self.batch, C.byref(self.config),
                   C.byref(self.tables), seed, self.obs.data_ptr(), self.mask.data_ptr(),
                   self.stream, self.device.type == 'cuda'))
        return self.obs

    def step(self, actions):
        assert actions.device == self.device and actions.dtype == torch.int64 and actions.is_contiguous()
        self.check(self.lib.learn_v2_step(self.state.data_ptr(), self.batch, C.byref(self.config),
                   C.byref(self.tables), actions.data_ptr(), self.limit, self.obs.data_ptr(),
                   self.mask.data_ptr(), self.out.data_ptr(), self.stream, self.device.type == 'cuda'))
        return self.obs, self.out

    def heuristic(self):
        self.check(self.lib.learn_v2_heuristic(self.state.data_ptr(), self.batch, C.byref(self.config),
                   C.byref(self.tables), self.actions.data_ptr(), self.stream,
                   self.device.type == 'cuda'))
        return self.actions
