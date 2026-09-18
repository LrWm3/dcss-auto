"""Prepared-observation-only navigation baseline. No training or route inputs."""
import argparse,ctypes as C,hashlib,json,subprocess
from pathlib import Path
import numpy as np
import torch
from run import evaluate,save_json
from runtime import OUT,ROOT
from fullsize_navigation import FullEnv,build_full
from native_curriculum import factory
from symbolic_fast import FastSymbolicPolicy

HERE=Path(__file__).resolve().parent

def build():
    source=HERE/'observation_teacher.cpp';lib=OUT/'observation-teacher.so';stamp=OUT/'observation-teacher.sha256'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if not lib.exists() or not stamp.exists() or stamp.read_text()!=digest:
        subprocess.run(['g++','-O3','-std=c++17','-shared','-fPIC',str(source),'-o',str(lib)],check=True)
        stamp.write_text(digest)
    return lib

class PreparedTeacher:
    """Only these already-prepared arrays cross the planner's API boundary."""
    def __init__(self,remember=True):
        self.lib=C.CDLL(str(build()));self.remember=remember;self.handle=None;self.n=0
        self.lib.obs_teacher_new.argtypes=[C.c_int,C.c_int];self.lib.obs_teacher_new.restype=C.c_void_p
        self.lib.obs_teacher_delete.argtypes=[C.c_void_p]
        self.lib.obs_teacher_step.argtypes=[C.c_void_p]*5
    def reset(self):
        if self.handle:self.lib.obs_teacher_delete(self.handle)
        self.handle=None;self.n=0
    def __del__(self):self.reset()
    def actions(self,local,global_map,mask):
        local=np.ascontiguousarray(local,dtype=np.float32);global_map=np.ascontiguousarray(global_map,dtype=np.float32);mask=np.ascontiguousarray(mask,dtype=np.float32)
        n=len(local);assert local.shape==(n,5,15,15) and global_map.shape==(n,6,16,16) and mask.shape==(n,19)
        assert np.isfinite(local).all() and np.isfinite(global_map).all()
        if self.handle is None:self.handle=self.lib.obs_teacher_new(n,int(self.remember));self.n=n
        assert n==self.n
        actions=np.empty(n,np.int64)
        self.lib.obs_teacher_step(self.handle,local.ctypes.data,global_map.ctypes.data,mask.ctypes.data,actions.ctypes.data)
        assert np.all(mask[np.arange(n),actions]>0)
        return actions

class Policy:
    def __init__(self,remember=True):
        # This is the exact same preprocessing used by the learner. Its random
        # network weights are never executed; only prepare() is used.
        self.preparer=FastSymbolicPolicy(True,True,True).cuda();self.teacher=PreparedTeacher(remember)
    def reset_cache(self):self.teacher.reset()
    @torch.no_grad()
    def __call__(self,g,mask,stats,intervene=None):
        assert intervene is None
        local,glob,_,_=self.preparer.prepare(g,stats)
        actions=self.teacher.actions(local.cpu().numpy(),glob.cpu().numpy(),mask.cpu().numpy())
        out=torch.zeros_like(mask);out.scatter_(1,torch.from_numpy(actions).to(mask.device)[:,None],1.)
        return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--split',choices=['validation','test'],default='validation');args=ap.parse_args()
    torch.set_num_threads(1);build_full()
    report=dict(scope='Enemy-free navigation. The planner receives ONLY prepared 15x15 local categories/stairs, 16x16 coarse fractions/stairs/player-bin, and action masks. It never receives exact global XY, raw map, simulator state, scene/map IDs, teacher labels or route distances. Fixed 80x70 dimensions are public constants. History tracks repeated observations, own deterministic choices and coarse-bin visits; no assumed motion or hidden-map stitching.',cpp_sha256=hashlib.sha256((HERE/'observation_teacher.cpp').read_bytes()).hexdigest(),split=args.split,deadline=1024,results={})
    for name,policy,teacher in [('stateless',Policy(False),False),('history',Policy(True),False),('exact_reference',None,True)]:
        report['results'][name]={}
        for band,cls in [('middle',factory(1)),('longer',FullEnv)]:
            r=evaluate(policy,args.split,limit=1024,teacher=teacher,env_class=cls)
            report['results'][name][band]=r
            save_json(ROOT/'results'/f'observation-teacher-{args.split}.json',report)
            print(name,band,r['summary'],flush=True)
    report['finished']=True;save_json(ROOT/'results'/f'observation-teacher-{args.split}.json',report)
if __name__=='__main__':main()
