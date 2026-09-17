"""Reuse anonymous simulator; add curriculum resets through an isolated library."""
import ctypes as C
import importlib.util
import json
import subprocess
from pathlib import Path
import torch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('anonymous_runtime',HERE.parent/'d1-anonymous-power/runtime.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
ROOT=a.ROOT;SUITE=ROOT/'learning-runs/d1-sleeper-bypass';OBS=a.OBS
SOURCE=a.SUITE/'varied/checkpoints/5000192.pt'
Store=a.Store;weights=a.weights;ReplayAnchor=a.ReplayAnchor;digest=a.digest
MIX=0

def load_model(path=SOURCE):return a.load_model(path)

def build():
    a.build();SUITE.mkdir(exist_ok=True)
    files=[HERE/'native.cu',a.HERE/'native.cu',a.PRIOR/'single_enemy.cu',a.PRIOR/'hooks.cu',a.PRIOR/'learn.cu',ROOT/'branches/d1-stairs-v2/src/sim.h']
    fp={str(p):digest(p) for p in files};meta=SUITE/'build.json'
    if meta.exists() and json.loads(meta.read_text())==fp and (SUITE/'bypass.so').exists():return
    subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*a.base.FLAGS,'-DCLUMP_MODE=0',str(HERE/'native.cu'),'-o',str(SUITE/'bypass.so')],check=True)
    meta.write_text(json.dumps(fp,indent=2))

class Env(a.Env):
    def __init__(self,*args,**kwargs):
        self.training=kwargs.get('varied',False)
        self.mix=MIX if kwargs.get('varied',False) else 0
        super().__init__(*args,**kwargs)
        self.ext=C.CDLL(str(SUITE/'bypass.so'));p=C.c_void_p;i=C.c_int
        self.ext.bypass_inject.argtypes=[p,i,p,p,p,p,p,p,i,i,p]
        self.ext.bypass_inspect.argtypes=[p,i,p,p,p]
        self.tags=torch.zeros(self.batch,dtype=torch.int32,device=self.device)
        self.completed=torch.zeros(2,4,device=self.device)
        if self.mix:self.inject(initial=True)
    def inject(self,initial=False,percent=None):
        self.check(self.ext.bypass_inject(self.state.data_ptr(),self.batch,C.byref(self.config),C.byref(self.tables),self.obs.data_ptr(),self.mask.data_ptr(),self.out.data_ptr(),self.tags.data_ptr(),int(initial),self.mix if percent is None else percent,self.stream))
    def step(self,actions,active=None):
        obs,out=super().step(actions,active)
        if self.training and active is None:
            for kind in [0,1]:
                done=(self.tags==kind)&out[:,1].bool()
                self.completed[kind]+=torch.stack([done.sum(),(out[:,2]*done).sum(),(out[:,6]*done).sum(),(out[:,7]*done).sum()])
            if self.mix:self.inject()
        return obs,out
    def inspect(self):
        out=torch.empty(self.batch,5632,device=self.device,dtype=torch.int32)
        self.check(self.ext.bypass_inspect(self.state.data_ptr(),self.batch,C.byref(self.tables),out.data_ptr(),self.stream));return out.cpu()
