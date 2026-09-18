"""Variable-strength routing screen, isolated from all previous environments."""
import ctypes as C
import hashlib,json,subprocess
from pathlib import Path
import numpy as np
import torch
from run import save_json
from runtime import Env,ROOT,OUT,HERE,old
from fullsize_navigation import FOLDER,generate,read_map

FOLDER_OUT=OUT/'route-threat'

def build():
    generate();FOLDER_OUT.mkdir(exist_ok=True)
    paths=[HERE/'route_threat_native.cu',HERE/'native.cu',HERE.parent/'d1-stat-generalization/learn.cu',ROOT/'branches/d1-stairs-v2/src/sim.h']
    signature=hashlib.sha256(b''.join(p.read_bytes() for p in paths)).hexdigest()
    lib=FOLDER_OUT/'threat.so';stamp=FOLDER_OUT/'build.sha256'
    if not lib.exists() or not stamp.exists() or stamp.read_text()!=signature:
        subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*old.FLAGS,'-DCLUMP_MODE=1',str(paths[0]),'-o',str(lib)],check=True)
        stamp.write_text(signature)
    return lib

class ThreatEnv(Env):
    def __init__(self,split='train',batch=32,map_dir=None):
        super().__init__(split,batch,map_dir=map_dir or FOLDER/'maps',grid_shape=(70,80),library=FOLDER_OUT/'threat.so')
        d=json.loads((HERE.parent/'d1-anonymous-power/distribution.json').read_text())
        self.profiles=torch.tensor(d['vectors'][:d['training_profiles']],device='cuda',dtype=torch.int32)
        self.tables.profiles=self.profiles.data_ptr();self.tables.profile_count=len(self.profiles);self.tables.varied=1
        self.memory=torch.empty(batch,self.lib.threat_memory_bytes(),device='cuda',dtype=torch.uint8)
        self.grid=torch.empty(batch,14,70,80,device='cuda',dtype=torch.uint8);self.stats=torch.empty(batch,7,device='cuda')
        p=C.c_void_p;i=C.c_int
        self.lib.threat_init.argtypes=[p,p,i,p,p,C.c_uint64,p]
        self.lib.threat_export.argtypes=[p,p,i,p,p,p,p,p,p]
        self.lib.threat_step.argtypes=[p,p,i,p,p,p,p,i,p,p]
        self.lib.threat_scene.argtypes=[p,p,i,p,p,p,p,p,C.c_uint64,p]
    def reset(self,seed=0,ids=None,power=None):
        self.active.fill_(True);self.out.zero_()
        if ids is None:
            self.check(self.lib.threat_init(self.state.data_ptr(),self.memory.data_ptr(),self.batch,C.byref(self.config),C.byref(self.tables),seed,self.stream))
        else:
            ids=ids.int().contiguous();power=power.int().contiguous()
            self.check(self.lib.threat_scene(self.state.data_ptr(),self.memory.data_ptr(),self.batch,C.byref(self.config),C.byref(self.tables),self.scenes.data_ptr(),ids.data_ptr(),power.data_ptr(),seed,self.stream))
        self.observe()
    def observe(self,labels=False):
        self.check(self.lib.threat_export(self.state.data_ptr(),self.memory.data_ptr(),self.batch,C.byref(self.tables),self.grid.data_ptr(),self.mask.data_ptr(),self.stats.data_ptr(),self.meta.data_ptr(),self.stream))
    def step(self,actions,limit=2048,labels=False):
        self.check(self.lib.threat_step(self.state.data_ptr(),self.memory.data_ptr(),self.batch,C.byref(self.config),C.byref(self.tables),actions.long().contiguous().data_ptr(),self.active.data_ptr(),limit,self.out.data_ptr(),self.stream))
        self.active &= ~self.out[:,1].bool();self.observe()

def pressure_maps():
    """Reuse exact previous held-out backtracking geometry; no training exposure."""
    folder=FOLDER_OUT/'pressure';folder.mkdir(exist_ok=True)
    target=folder/'test.npz'
    if target.exists():return folder
    import importlib.util
    spec=importlib.util.spec_from_file_location('backtrack_maps',HERE.parent/'d1-backtrack/maps.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    source=ROOT/'learning-runs/d1-backtrack/maps'
    if not (source/'manifest.json').exists():mod.generate(source)
    arrays=[];rows=[]
    for mid in range(32):
        arrays.append(read_map(source/f'map-{mid:03d}.bin'))
        length=mod.LENGTHS[mid//8];sym=mid%8
        def pos(x,y):
            xx,yy=mod.xy(x,y,sym);return yy*80+xx
        for known in [0,1]:
            history=([pos(-length,y) for y in range(-12,1)] if known else [pos(-length,0)])+[pos(x,0) for x in range(-length+1,1)]
            row=[mid,known,pos(0,0),*[pos(-length,y) for y in [-12,-16,-20]],pos(7,0),len(history),*history]
            rows.append(row+[-1]*(264-len(row)))
    nc=np.array([len(a[3]) for a in arrays],np.int32)
    np.savez_compressed(target,floor=np.stack([a[0] for a in arrays]),cells=np.stack([a[1] for a in arrays]),index=np.stack([a[2] for a in arrays]),distance=np.concatenate([a[3] for a in arrays]),los=np.stack([a[4] for a in arrays]),ncells=nc,offsets=np.r_[0,np.cumsum(nc[:-1])].astype(np.int32),scenarios=np.array(rows,np.int32))
    return folder
