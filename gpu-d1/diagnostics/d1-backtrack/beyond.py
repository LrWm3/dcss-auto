"""Frozen policies: known stairs beyond a dangerous sleeping corridor blocker."""
import argparse
import ctypes as C
import json
import subprocess
import time
import torch
import run as base
from maps import generate
r=base.r;HERE=base.HERE;ROOT=base.ROOT
base.OUT=ROOT/'learning-runs/d1-stairs-beyond-enemy';OUT=base.OUT

def configure(awake=False,passable=False):
    global OUT
    OUT=ROOT/('learning-runs/d1-stairs-beyond-enemy-awake' if awake else 'learning-runs/d1-stairs-beyond-enemy')
    if passable:OUT=ROOT/(str(OUT.relative_to(ROOT))+'-passable')
    base.OUT=OUT

class Env(base.Env):
    def __init__(self,reps=32,awake=False):
        self.awake=awake
        super().__init__(reps=reps)
        fn=self.lib.beyond_setup_awake if awake else self.lib.beyond_setup
        fn.argtypes=self.setup_fn.argtypes
        self.setup_fn=fn
    def setup(self):
        self.check(self.setup_fn(self.state.data_ptr(),self.batch,C.byref(self.config),C.byref(self.tables),self.reps,819911,self.obs.data_ptr(),self.mask.data_ptr(),self.checks.data_ptr(),self.stream))
        assert (self.checks[:,0]==1).all() and (self.checks[:,3]==3).all()
        assert (self.obs[:,1000]==1).all()
        assert (self.obs[:,1006:1014]==self.obs[:,725:733]).all()
        strong=(torch.arange(self.batch,device='cuda')//self.reps)%3==2
        assert (self.measure()[strong,2]==int(self.awake)).all()
        assert (self.obs[strong,959]==(-1 if self.awake else 1)).all()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--awake',action='store_true');parser.add_argument('--passable',action='store_true');args=parser.parse_args();configure(args.awake,args.passable)
    torch.set_num_threads(1);OUT.mkdir(exist_ok=True);start=time.monotonic()
    manifest=generate(OUT/'maps',stairs_beyond=True,passable=args.passable)
    subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*r.base.FLAGS,'-DCLUMP_MODE=0',str(HERE/'beyond.cu'),'-o',str(OUT/'backtrack.so')],check=True)
    e=Env(awake=args.awake);e.setup();print('setup verified',time.monotonic()-start,flush=True)
    paths={'source5m':r.SUITE/'varied/checkpoints/5000192.pt','control6m':ROOT/'learning-runs/d1-sleeper-bypass/control/checkpoints/1000448.pt','practice6m':ROOT/'learning-runs/d1-sleeper-bypass/practice/checkpoints/1000448.pt'}
    report=dict(schema=1,maps=manifest,checkpoints={k:dict(path=str(v),sha256=r.digest(v)) for k,v in paths.items()},repeats=32,arms={},notes=[
        'Player at x=0; sleeper at x=7; first stair at x=7+D, D=4/8/16/24. Other stairs are one/two tiles off that endpoint.',
        'One-tile corridor: cannot pass the enemy while it occupies the corridor; no safe alternate route to stairs is supplied.',
        'History walks from x=-8 to stairs and back before the sleeper is inserted. This synthetic encounter intervention supplies real remembered terrain and stair observations.',
        'All three stairs known; frontier lies in unexplored branch beyond enemy. Stair and frontier route directions both initially point toward enemy.',
        'Player full HP18/damage4; enemy none, weak HP6/damage4, or strong HP24/damage20; usual LOS/wake rules.',
        'Deadline 2048 physical turns includes 8+2*(7+D) history turns. All policy actions free after setup.',
        'Eight rotations/reflections; three frozen checkpoints, greedy and sampled. No claim that strong-enemy deaths are avoidable.'
    ])
    report['passable']=args.passable
    if args.passable:
        report['notes'][1]='Corridor widens to a fully remembered 7x5 room at x=4..10,y=-2..2 around the enemy at x=7,y=0. Space permits passing around the enemy, including when awake; safe passage is not guaranteed.'
    report['strong_starts_awake']=args.awake
    if args.awake:
        report['notes'].append('Only the strong enemy starts awake; weak and no-enemy controls unchanged. Starting energy remains 70, identical to sleeping variant.')
        # Paired setup check: observations differ only in the strong enemy sleep
        # field; legal actions and all other observation fields remain identical.
        sleeping=Env();sleeping.setup();awake_obs=e.obs.clone()
        strong=(torch.arange(e.batch,device='cuda')//e.reps)%3==2
        awake_obs[strong,959]=sleeping.obs[strong,959]
        assert torch.equal(awake_obs,sleeping.obs) and torch.equal(e.mask,sleeping.mask)
        report['paired_observation_check']='Only strong enemy sleep field differs; all other observations and action masks identical.'
    for name,path in paths.items():
        model=r.load_model(path)
        for mode in ['greedy','sampled']:
            rows=base.evaluate(e,model,mode)
            for row in rows:
                distance=row.pop('backtrack');row['stairs_beyond_enemy']=distance
                row['post_start_turns']=row['turns']-(8+2*(7+distance))
                for key in ['returned_to_junction','reached_unseen_alternative','discovered_stairs']:row.pop(key)
            report['arms'][name+'_'+mode]=rows;report['wall_seconds']=time.monotonic()-start
            (OUT/'result.json').write_text(json.dumps(report,indent=2))
            print(name,mode,{key:sum(x[key] for x in rows if x['enemy']=='strong') for key in ['exits','deaths','timeouts']},report['wall_seconds'],flush=True)
    report['complete']=True;(OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
