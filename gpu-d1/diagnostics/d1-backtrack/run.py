"""Frozen-policy backtracking screen with real observation history and native LOS."""
import argparse
import ctypes as C
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import torch
from maps import generate,LENGTHS
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];OUT=ROOT/'learning-runs/d1-backtrack'
spec=importlib.util.spec_from_file_location('anonymous_runtime',HERE.parent/'d1-anonymous-power/runtime.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
REPS=32

class Env(r.Env):
    def __init__(self,reps=REPS,known_stairs=False):
        self.known_stairs=known_stairs
        self.reps=reps;batch=32*3*reps
        self.profile_tensor=torch.tensor(r.distribution()['vectors'],dtype=torch.int32,device='cuda')
        self.assignment_tensor=torch.full((batch,),4,dtype=torch.int32,device='cuda');self.varied=False;self.seed_period=batch
        r.base.BaseEnv.__init__(self,batch,24,seed=418,device='cuda',corpus=OUT/'maps',map_limit=32,map_filter=-2,library_path=OUT/'backtrack.so')
        p=C.c_void_p;i=C.c_int
        self.setup_fn=self.lib.backtrack_setup_known if known_stairs else self.lib.backtrack_setup
        self.setup_fn.argtypes=[p,i,p,p,i,C.c_uint64,p,p,p,p]
        self.lib.backtrack_measure_api.argtypes=[p,i,i,p,p]
        self.lib.bypass_verify.argtypes=[p,i,p,p,p,p,p]
        self.checks=torch.empty(batch,4,device='cuda',dtype=torch.int32)
        self.measurements=torch.empty(batch,5,device='cuda',dtype=torch.int32)
    def setup(self):
        self.check(self.setup_fn(self.state.data_ptr(),self.batch,C.byref(self.config),C.byref(self.tables),self.reps,819911,self.obs.data_ptr(),self.mask.data_ptr(),self.checks.data_ptr(),self.stream))
        assert (self.checks[:,0]==1).all(),'Nearest frontier does not point toward threat'
        assert (self.checks[:,3]==(2 if self.known_stairs else 0)).all()
        from maps import xy
        directions=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]
        forward=[]
        for case in range(96):
            g=case//3%8;p=xy(0,0,g);q=xy(1,0,g)
            forward.extend([directions.index((q[0]-p[0],q[1]-p[1]))]*self.reps)
        expected=torch.tensor(forward,device='cuda')
        assert (self.obs[:,725:733].sum(1)==1).all()
        assert (self.obs[:,725:733].argmax(1)==expected).all(), 'Observed frontier must point forward'
        if self.known_stairs:
            assert (self.obs[:,1000]>0).all(), 'Missing known-stair target'
            assert (self.obs[:,1006:1014].argmax(1)!=self.obs[:,725:733].argmax(1)).all(), 'Stair and frontier cues should disagree'
    def measure(self):
        self.check(self.lib.backtrack_measure_api(self.state.data_ptr(),self.batch,self.reps,self.measurements.data_ptr(),self.stream));return self.measurements

@torch.no_grad()
def evaluate(e,model,mode):
    e.setup();n=e.batch;active=torch.ones(n,device='cuda',dtype=torch.bool)
    terminal=torch.zeros(n,7,device='cuda');waits=torch.zeros(n,device='cuda');longest=waits.clone();streak=waits.clone()
    woke=active&False;backtracked=woke.clone();explored_other=woke.clone();found=woke.clone();entered_danger=woke.clone()
    max_back=waits.clone();first=e.obs.clone();dist=model(first,e.mask)[0];prob=dist.probs.cpu();action=dist.greedy().cpu()
    actions=torch.full((n,),16,device='cuda',dtype=torch.long);torch.manual_seed(819911)
    length=torch.tensor([LENGTHS[(j//e.reps)//24] for j in range(n)],device='cuda')
    for tick in range(2048):
        z=e.measure();woke|=active&z[:,2].bool();found|=active&(z[:,3]>0)
        backtracked|=active&(z[:,0]<=-length+1);explored_other|=active&(z[:,1]<-7);entered_danger|=active&(z[:,0]>=1)
        max_back=torch.maximum(max_back,torch.where(active,-z[:,0].float(),0))
        ix=torch.where(active)[0];d=model(e.obs[ix],e.mask[ix])[0];a=d.greedy() if mode=='greedy' else d.sample();actions[ix]=a
        waits[ix]+=(a==16);streak[ix]=torch.where(a==16,streak[ix]+1,0);longest[ix]=torch.maximum(longest[ix],streak[ix])
        e.step(actions,active=active);end=active&e.out[:,1].bool()
        terminal[end]=e.out[end][:,[2,6,7,5,3,49,43]];found|=end&(e.out[:,43]>=0)
        # Cumulative kills/damage preserve terminal combat evidence after autoreset.
        woke|=end&((e.out[:,3]>0)|(e.out[:,49]>0));active&=~end
        if not active.any():break
    assert not active.any() and (terminal[:,:3].sum(1)==1).all()
    rows=[]
    for case in range(96):
        sl=slice(case*e.reps,(case+1)*e.reps);z=terminal[sl].cpu();p=prob[sl];a=action[sl]
        row={'backtrack':LENGTHS[case//24],'symmetry':case//3%8,'enemy':['none','weak','strong'][case%3],'episodes':e.reps}
        row.update({k:int(z[:,j].sum()) for j,k in enumerate(['exits','deaths','timeouts'])})
        row.update(turns=float(z[:,3].mean()),exit_without_kill=int(((z[:,0]>0)&(z[:,4]==0)).sum()),mean_damage=float(z[:,5].mean()),initial_wait_probability=float(p[:,16].mean()),initial_greedy_waits=int((a==16).sum()))
        for k,v in [('woke_enemy',woke),('returned_to_junction',backtracked),('reached_unseen_alternative',explored_other),('discovered_stairs',found),('entered_danger_branch',entered_danger)]:row[k]=int(v[sl].sum())
        for k,v in [('wait_actions',waits),('longest_wait_streak',longest),('maximum_backtrack',max_back)]:row[k]=float(v[sl].mean())
        if e.known_stairs:
            row['reached_return_branch']=row.pop('reached_unseen_alternative')
            row['post_start_turns']=row['turns']-row['backtrack']-12
        rows.append(row)
    return rows

def main():
    global OUT
    parser=argparse.ArgumentParser();parser.add_argument('--known-stairs',action='store_true');args=parser.parse_args()
    if args.known_stairs:OUT=ROOT/'learning-runs/d1-backtrack-known-stairs'
    torch.set_num_threads(1);OUT.mkdir(exist_ok=True);start=time.monotonic()
    manifest=generate(OUT/'maps');print('maps_ready',time.monotonic()-start,flush=True)
    subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*r.base.FLAGS,'-DCLUMP_MODE=0',str(HERE/'native.cu'),'-o',str(OUT/'backtrack.so')],check=True)
    e=Env(reps=2,known_stairs=args.known_stairs);e.setup();tags=torch.ones(e.batch,device='cuda',dtype=torch.int32);verified=torch.zeros_like(tags)
    e.check(e.lib.bypass_verify(e.state.data_ptr(),e.batch,C.byref(e.config),C.byref(e.tables),tags.data_ptr(),verified.data_ptr(),e.stream))
    assert (verified==1).all();print('preflight_verified',int(verified.sum()),time.monotonic()-start,flush=True)
    paths={'source5m':r.SUITE/'varied/checkpoints/5000192.pt','control6m':ROOT/'learning-runs/d1-sleeper-bypass/control/checkpoints/1000448.pt','practice6m':ROOT/'learning-runs/d1-sleeper-bypass/practice/checkpoints/1000448.pt'}
    report=dict(schema=1,maps=manifest,checkpoints={k:dict(path=str(v),sha256=r.digest(v)) for k,v in paths.items()},repeats=REPS,preflight_verified=192,arms={},notes=['Single-step controls not imposed: all policy actions are free.','History is an actual walk from the junction to the current location; nearest frontier points into the dangerous branch.','Known return corridor leads to a separate unseen frontier; all stairs start hidden.','One dangerous or weak sleeper, or no-enemy control; all stats and observations use the anonymous simulator.','Eight symmetry orientations include reflections of the L-shaped corridor.','Reported turns include the preceding walk of4/8/16/24 turns.'])
    if args.known_stairs:
        report['known_stairs']=True
        report['notes']=[
            'Same geometry, stats, policies and frontier direction as the unknown-stairs screen.',
            'History starts on the first stair, walks 12 tiles to the junction, then to the test location. Two stairs and a connected route are known.',
            'Actual history costs 12 extra turns versus unknown-stairs; deadline stays 2048. No policy actions are imposed after setup.',
            'Known stairs enable the existing stair direction feature. This tests destination knowledge plus its existing navigation guide together.',
            'The far dangerous dead end remains unseen; nearest frontier still points past the enemy.',
            'reached_return_branch is a geometric threshold, not newly discovered terrain; discovered_stairs is true at setup.'
        ]
    e=Env(known_stairs=args.known_stairs)
    for name,path in paths.items():
        model=r.load_model(path)
        for mode in ['greedy','sampled']:
            report['arms'][name+'_'+mode]=evaluate(e,model,mode)
            report['wall_seconds']=time.monotonic()-start
            (OUT/'result.json').write_text(json.dumps(report,indent=2))
            print(name,mode,'exits',sum(x['exits'] for x in report['arms'][name+'_'+mode]),'seconds',report['wall_seconds'],flush=True)
    report['complete']=True;(OUT/'result.json').write_text(json.dumps(report,indent=2));print('complete',report['wall_seconds'],flush=True)

if __name__=='__main__':main()
