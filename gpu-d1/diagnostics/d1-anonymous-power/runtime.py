"""Anonymous, common-speed continuation with calibrated per-enemy stats."""
import ctypes as C
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import torch

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PRIOR=HERE.parent/'d1-stat-generalization'
spec=importlib.util.spec_from_file_location('stat_runtime',PRIOR/'runtime.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
SOURCE=base.SOURCE
SUITE=ROOT/'learning-runs/d1-anonymous-power'
OBS=base.OBS
Tables=base.Tables
Store=base.Store
weights=base.weights
load_model=base.load_model
digest=base.digest
CORPUS=base.CORPUS

def distribution():return json.loads((HERE/'distribution.json').read_text())

def build():
    SUITE.mkdir(parents=True,exist_ok=True)
    files=[HERE/'native.cu',PRIOR/'single_enemy.cu',PRIOR/'hooks.cu',PRIOR/'learn.cu',ROOT/'branches/d1-stairs-v2/src/sim.h']
    fingerprint=dict(files={str(p):digest(p) for p in files},flags=base.FLAGS)
    target=SUITE/'native-build.json'
    if target.exists() and json.loads(target.read_text())==fingerprint and all((SUITE/f'power-{i}.so').exists() for i in [0,1]):return
    for clump in [0,1]:
        tmp=SUITE/f'power-{clump}.tmp.so'
        subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*base.FLAGS,f'-DCLUMP_MODE={clump}',str(HERE/'native.cu'),'-o',str(tmp)],check=True)
        tmp.replace(SUITE/f'power-{clump}.so')
    target.write_text(json.dumps(fingerprint,indent=2)+'\n')

class Env(base.Env):
    def __init__(self,split='train',assignments=None,batch=512,seed=0,varied=False,device='cuda',map_limit=None,seed_period=None,clump=None,balanced=None,vectors=None):
        if vectors is None:
            d=distribution();vectors=d['vectors'][:d['training_profiles']] if varied else d['vectors']
        self.profile_tensor=torch.tensor(vectors,dtype=torch.int32,device=device)
        self.assignment_tensor=torch.tensor(assignments if assignments is not None else [0]*batch,dtype=torch.int32,device=device)
        batch=len(self.assignment_tensor);self.varied=varied;self.seed_period=seed_period or batch
        if balanced is None:balanced=split!='train'
        base.BaseEnv.__init__(self,batch,24,seed=seed,device=device,corpus=CORPUS/split,map_limit=map_limit or {'train':256,'validation':32,'test':100}[split],map_filter=-2 if balanced else -1,library_path=SUITE/f'power-{int(split=="train") if clump is None else clump}.so')
        self.split=split;p,i=C.c_void_p,C.c_int
        self.lib.stats_metadata.argtypes=[p,i,p,p,i]
        self.lib.stats_reseed.argtypes=[p,i,C.c_uint64,p]
        self.lib.stats_observe.argtypes=[p,i,p,p,p,p,p,i]
        self.lib.stats_scene.argtypes=[p,i,p,p,i,i,i,p,p,p]
        self.lib.stats_restore_config.argtypes=[p,i,p,p,i,p,p,p]
        self.lib.stats_semantics.argtypes=[p,p]
        self.lib.single_scene_api.argtypes=[p,i,p,p,i,i,i,i,p,p,p]
        self.lib.single_rollout_api.argtypes=[p,i,p,p,i,p,p]
        self.lib.power_duels.argtypes=[p,p,i,i,C.c_uint64,p,p]
        self.lib.power_duel_check.argtypes=[p,p]
    def reset(self,seed):
        if not isinstance(self.tables,Tables):
            self.tables=Tables(self.profile_tensor.data_ptr(),self.assignment_tensor.data_ptr(),len(self.profile_tensor),int(self.varied),self.seed_period,*[getattr(self.tables,k) for k,_ in base.BaseTables._fields_])
        return base.BaseEnv.reset(self,seed)

def anonymous(x):
    x=x.clone();x[:,450:650].reshape(-1,40,5)[:,:,3]=0;return x

class ReplayAnchor(base.ReplayAnchor):
    def __init__(self,source):
        super().__init__(source)
        self.x=anonymous(self.x);self.rx=anonymous(self.rx)
        # Retain the source's anonymous-observation behavior on old replay;
        # never imitate its choices on newly generated dangerous rollout states.
        with torch.no_grad():self.rp=torch.cat([source(x,m)[0].probs for x,m in zip(self.rx.split(1024),self.rm.split(1024))])
