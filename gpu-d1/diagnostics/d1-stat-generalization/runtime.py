"""Isolated stat-generalization simulator, policy expansion, and frozen split."""
import ctypes as C
import hashlib
import itertools
import json
import math
import pathlib
import subprocess
import sys
import numpy as np
import torch
from torch import nn

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OLD=ROOT/'branches/d1-stairs-v2/scripts'
sys.path.insert(0,str(OLD))
from assets import FLAGS
from learn_env_ring_multi import Env as BaseEnv, Tables as BaseTables
from tactical_models import Policy as BasePolicy
from symmetry import D4 as BaseD4
from common import NavigationAnchor as OldAnchor, weights, CORPUS
from ablation_storage import Store
SUITE=ROOT/'learning-runs/d1-stat-generalization'
SOURCE=ROOT/'learning-runs/d1-stairs-survival-broad/targeted/checkpoints/3000320.pt'
OBS=1098


def digest(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def specification():
    levels=[[12,18,24],[3,4,5],[.75,1.,1.25],[.75,1.,1.25],[12,24,36]]
    grid=list(itertools.product(range(3),repeat=5));nom=(1,)*5
    axes={x for x in grid if sum(a!=1 for a in x)<=1}
    orbits={tuple(sorted(tuple((a+k)%3 for a in x) for k in range(3))) for x in grid}
    orbits=sorted(o for o in orbits if not axes.intersection(o))
    rng=np.random.default_rng(20260917);rng.shuffle(orbits)
    val=set(itertools.chain.from_iterable(orbits[:8]));test=set(itertools.chain.from_iterable(orbits[8:16]))
    train=set(grid)-val-test
    assert len(train)==195 and len(val)==len(test)==24 and axes<=train
    for held in [val,test]:
        for j in range(5):assert [sum(x[j]==a for x in held) for a in range(3)]==[8]*3
    for i,j in itertools.combinations(range(5),2):assert {(x[i],x[j]) for x in train}==set(itertools.product(range(3),repeat=2))
    order=[nom]+sorted(train-{nom})+sorted(val)+sorted(test)
    rows=[]
    def add(values,split,code=None,label=None):
        hp,damage,ehp,edmg,count=values
        vec=[int(hp),int(damage),int(count)]+[max(1,math.floor(v*ehp+.5)) for v in [8,10,12,16,12,10]]+[max(1,math.floor(v*edmg+.5)) for v in [3,3,1,5,5,3]]
        rows.append(dict(id=len(rows),code=code,values=values,vector=vec,split=split,label=label))
    for x in order:add([levels[j][a] for j,a in enumerate(x)],'train' if x in train else 'validation' if x in val else 'test',list(x))
    # Greedy max-min Hamming spread; deterministic and outcome-independent.
    mixed=sorted(train-axes);chosen=[]
    while len(chosen)<8:
        q=max(mixed,key=lambda x:(min(sum(a!=b for a,b in zip(x,y)) for y in chosen) if chosen else sum(a!=1 for a in x),x))
        chosen.append(q);mixed.remove(q)
    axids=[order.index(x) for x in sorted(axes)];mixids=[order.index(x) for x in chosen]
    panels=dict(validation=axids+mixids[:5]+list(range(195,219)),main=axids+mixids+list(range(219,243)))
    nominal=[18,4,1.,1.,24]
    for split,variations in [('interpolation',[(0,[15,21]),(2,[.875,1.125]),(4,[18,30])]),
                             ('extrapolation',[(0,[9,30]),(1,[2,6]),(2,[.5,1.5]),(3,[.5,1.5]),(4,[6,40])])]:
        panels[split]=[]
        for factor,values in variations:
            for value in values:
                v=nominal.copy();v[factor]=value
                panels[split].append(len(rows));add(v,split,label=f'factor{factor}={value}')
    assert len({tuple(r['vector']) for r in rows})==len(rows)
    assert len(panels['validation'])==40 and len(panels['main'])==43
    return dict(schema=1,seed=20260917,profiles=rows,panels=panels,train_profiles=195,nominal_episode_probability=.25)

SPEC=specification()

class Tables(C.Structure):
    _fields_=[('profiles',C.c_void_p),('assignments',C.c_void_p),('profile_count',C.c_int),('varied',C.c_int),('seed_period',C.c_int)]+BaseTables._fields_


def build():
    SUITE.mkdir(parents=True,exist_ok=True)
    hashes={str(p):digest(p) for p in [HERE/'learn.cu',HERE/'hooks.cu',ROOT/'branches/d1-stairs-v2/src/sim.h']}
    fingerprint=dict(files=hashes,flags=FLAGS)
    path=SUITE/'native-build.json'
    if path.exists() and json.loads(path.read_text())==fingerprint and all((SUITE/f'stats-clump{c}.so').exists() for c in [0,1]):return
    for clump in [0,1]:
        subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*FLAGS,f'-DCLUMP_MODE={clump}',str(HERE/'hooks.cu'),'-o',str(SUITE/f'stats-clump{clump}.so')],check=True)
    path.write_text(json.dumps(fingerprint,indent=2)+'\n')

class Env(BaseEnv):
    def __init__(self,split='train',assignments=None,batch=512,seed=0,varied=False,device='cuda',map_limit=None,seed_period=None,clump=None,balanced=None):
        self.profile_tensor=torch.tensor([r['vector'] for r in SPEC['profiles']],dtype=torch.int32,device=device)
        self.assignment_tensor=torch.tensor(assignments if assignments is not None else [0]*batch,dtype=torch.int32,device=device)
        batch=len(self.assignment_tensor);self.varied=varied;self.seed_period=seed_period or batch
        if balanced is None:balanced=split!='train'
        super().__init__(batch,24,seed=seed,device=device,corpus=CORPUS/split,map_limit=map_limit or {'train':256,'validation':32,'test':100}[split],map_filter=-2 if balanced else -1,library_path=SUITE/f'stats-clump{int(split=="train") if clump is None else clump}.so')
        self.split=split
        p,i=C.c_void_p,C.c_int
        self.lib.stats_metadata.argtypes=[p,i,p,p,i]
        self.lib.stats_reseed.argtypes=[p,i,C.c_uint64,p]
        self.lib.stats_observe.argtypes=[p,i,p,p,p,p,p,i]
        self.lib.stats_scene.argtypes=[p,i,p,p,i,i,i,p,p,p]
        self.lib.stats_restore_config.argtypes=[p,i,p,p,i,p,p,p]
        self.lib.stats_semantics.argtypes=[p,p]
    def reset(self,seed):
        if not isinstance(self.tables,Tables):
            self.tables=Tables(self.profile_tensor.data_ptr(),self.assignment_tensor.data_ptr(),195 if self.varied else len(SPEC['profiles']),int(self.varied),self.seed_period,*[getattr(self.tables,k) for k,_ in BaseTables._fields_])
        return super().reset(seed)
    def metadata_tensor(self):
        out=torch.empty(self.batch,18,dtype=torch.int64,device=self.device)
        self.check(self.lib.stats_metadata(self.state.data_ptr(),self.batch,out.data_ptr(),self.stream if self.device.type=='cuda' else None,int(self.device.type=='cuda')))
        return out
    def observe(self):
        self.check(self.lib.stats_observe(self.state.data_ptr(),self.batch,C.byref(self.config),C.byref(self.tables),self.obs.data_ptr(),self.mask.data_ptr(),self.stream if self.device.type=='cuda' else None,int(self.device.type=='cuda')))
    def reseed(self,seed):
        self.check(self.lib.stats_reseed(self.state.data_ptr(),self.batch,seed,self.stream))
    def scene(self,kind,hp_percent=100,profile=0):
        self.check(self.lib.stats_scene(self.state.data_ptr(),self.batch,C.byref(self.config),C.byref(self.tables),kind,hp_percent,profile,self.obs.data_ptr(),self.mask.data_ptr(),self.stream))

class D4(BaseD4):
    def observation(self,obs,groups):
        return torch.cat((super().observation(obs[:,:1015],groups),obs[:,1015:]),1)

class Policy(BasePolicy):
    def __init__(self):
        super().__init__('d4_exact',128)
        first=self.body[0]
        first.weight=nn.Parameter(torch.cat((first.weight.detach(),torch.zeros(128,83)),1));first.in_features=OBS
    def forward(self,obs,mask,temperature=None):
        if self.d4 is None:self.d4=D4(obs.device)
        return super().forward(obs,mask,temperature)


def load_model(path=SOURCE):
    m=Policy().cuda();w=torch.load(path,map_location='cpu',weights_only=False)['model']
    if w['body.0.weight'].shape[1]==1015:
        w=dict(w);w['body.0.weight']=torch.nn.functional.pad(w['body.0.weight'],(0,83))
    m.load_state_dict(w);return m.eval()


def nominal_obs(obs):
    """Append real nominal stats, inferred only for the already-visible records."""
    obs=obs[:,:1015]
    extra=torch.zeros(len(obs),83,device=obs.device)
    extra[:,0]=obs[:,650];extra[:,1:3]=1
    records=obs[:,450:650].reshape(-1,40,5)
    kinds=(records[:,:,3]*5).round().long().clamp(0,5);visible=records[:,:,4]
    hp=torch.tensor([8,10,12,16,12,10],device=obs.device)/16
    damage=torch.tensor([3,3,1,5,5,3],device=obs.device)/5
    extra[:,3:].reshape(-1,40,2)[:,:,0]=hp[kinds]*visible
    extra[:,3:].reshape(-1,40,2)[:,:,1]=damage[kinds]*visible
    return torch.cat((obs,extra),1)

class ReplayAnchor:
    def __init__(self,source):
        old=OldAnchor()
        eligible=(old.obs[:,959:999]>=0).all(-1)&(old.obs[:,999]==0)
        self.x=nominal_obs(old.obs[eligible]);self.mask=old.mask[eligible]
        with torch.no_grad():self.target=torch.cat([old.reference(x[:,:1015],m)[0].probs for x,m in zip(self.x.split(1024),self.mask.split(1024))])
        b=torch.load(ROOT/'learning-runs/d1-stairs-survival/bank.pt',weights_only=False)
        self.rx=nominal_obs(b['replay_obs'].cuda());self.rm=b['replay_mask'].cuda()
        with torch.no_grad():self.rp=torch.cat([source(x,m)[0].probs for x,m in zip(self.rx.split(1024),self.rm.split(1024))])
        del old,b
    def loss(self,model):
        result=0
        for x,m,p,weight in [(self.x,self.mask,self.target,1.),(self.rx,self.rm,self.rp,.5)]:
            ix=torch.randint(len(x),(256,),device='cuda');q=model(x[ix],m[ix])[0].probs
            result=result+weight*(p[ix]*(p[ix].clamp_min(1e-30).log()-q.clamp_min(1e-30).log())).sum(-1).mean()
        return result
