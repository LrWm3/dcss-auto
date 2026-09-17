"""Repeat the sleeping-enemy probes with current actions and sleep-aware REST."""
import ctypes as C
import json
import subprocess
import time
import numpy as np
import torch
import scenario_recheck as sr
from assets import FLAGS
from learn_env_ring_multi import Env


def conditions():
    rows=[]
    for geometry,xy in [('wake_plus_one',(7,1)),('vision_edge',(7,0)),('outside_vision',(8,0))]:
        for hp in [2,9,18]:
            for difficulty,kind,enemy_hp in [('reference',3,28),('hard',4,48)]:
                for orientation in range(8):
                    x,y=xy
                    if orientation>=4:x=-x
                    for _ in range(orientation%4):x,y=-y,x
                    rows.append(dict(geometry=geometry,hp=hp,difficulty=difficulty,kind=kind,enemy_hp=enemy_hp,orientation=orientation,x=x,y=y))
    return rows


@torch.no_grad()
def main():
    torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
    start=time.monotonic();paths,models=sr.policies();work=sr.WORK/'healing';work.mkdir(parents=True,exist_ok=True)
    source=sr.ROOT/'diagnostics/rest-recovery/probe.cu'
    text=source.read_text();text='#include "'+str(sr.NATIVE)+'"\n'+text.split('#endif\n',1)[1]
    cu=work/'probe.cu';cu.write_text(text);lib=work/'probe.so'
    subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*FLAGS,'-DCLUMP_MODE=0',str(cu),'-o',str(lib)],check=True)
    maps=sr.ROOT/'learning-runs/rest-sleep-recovery-probe/maps'
    if not (maps/'map-0.bin').exists():
        maps.mkdir(parents=True,exist_ok=True)
        sr.module('map_compile',sr.ROOT/'branches/vision15-choice-practice-v1/scripts/map_compile.py').compile_map({'floor':[(x,y) for x in range(-10,11) for y in range(-10,11)]},maps/'map-0.bin',0)
    rows=conditions();reps=32;n=len(rows)*reps
    env=Env(n,24,corpus=maps,library_path=lib)
    p,i=C.c_void_p,C.c_int
    env.lib.probe_init.argtypes=[p,i,p,p,p,i,p,p,p];env.lib.probe_read.argtypes=[p,i,p,p,p,p,p,p]
    params=torch.tensor([[r['hp'],r['kind'],r['enemy_hp'],r['x'],r['y']] for r in rows],dtype=torch.int32,device='cuda').repeat_interleave(reps,0).contiguous()
    state=torch.empty(n,5,device='cuda');approach=torch.empty(n,dtype=torch.int64,device='cuda')
    def read():env.check(env.lib.probe_read(env.state.data_ptr(),n,C.byref(env.config),C.byref(env.tables),params.data_ptr(),state.data_ptr(),approach.data_ptr(),env.stream))
    report=dict(training_performed=False,reps_per_orientation=reps,orientations=8,physical_turn_limit=2048,conditions=rows,checkpoints={name:sr.ec.digest(path) for name,path in paths.items()},native_sha256=sr.ec.digest(sr.NATIVE),probe_sha256=sr.ec.digest(cu),map_sha256=sr.ec.digest(maps/'map-0.bin'),arms={})
    for name,mode in [(name,mode) for name in models for mode in ['sampled','greedy']]+[(name,'scripted') for name in ['engage_now','heal_first','rest_first']]:
        env.check(env.lib.probe_init(env.state.data_ptr(),n,C.byref(env.config),C.byref(env.tables),params.data_ptr(),reps,env.obs.data_ptr(),env.mask.data_ptr(),env.stream));read()
        visible=torch.tensor([r['geometry']!='outside_vision' for r in rows],device='cuda').repeat_interleave(reps)
        assert torch.equal(state[:,2].bool(),visible) and not state[:,1].any()
        assert torch.equal(env.mask[:,17].bool(),params[:,0]<18)
        assert (env.obs[~visible,225:650]==0).all() and torch.equal(env.obs[:,959:].sum(1),visible.float())
        active=torch.ones(n,device='cuda',dtype=torch.bool);healed=params[:,0]>=18
        woke=torch.zeros_like(active)
        stats={k:torch.zeros(n,device='cuda') for k in ['clear','death','timeout','turns','rest_uses','waits_asleep','rest_before_wake','first_rest_probability','first_wait_probability']}
        wake_hp=torch.full((n,),float('nan'),device='cuda');torch.manual_seed(76031)
        for step in range(2048):
            idx=active.nonzero().flatten()
            if not len(idx):break
            if mode!='scripted':
                dist,_=models[name](env.obs[idx],env.mask[idx]);a=torch.full((n,),16,dtype=torch.int64,device='cuda')
                a[idx]=dist.greedy() if mode=='greedy' else dist.sample()
                if step==0:
                    stats['first_rest_probability'][idx]=dist.probs[:,17];stats['first_wait_probability'][idx]=dist.probs[:,16]
            else:
                a=approach.clone();direction=a.clamp_max(7)
                attacking=(a<8)&(env.mask.gather(1,(8+direction)[:,None]).squeeze(1)>0)
                a=torch.where(a==8,16,torch.where(attacking,a+8,a))
                if name=='heal_first':a[~healed]=16
                if name=='rest_first':a[(env.mask[:,17]>0)&~healed]=17
            assert ((env.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all()
            stats['waits_asleep']+=active&(state[:,1]==0)&(a==16)
            stats['rest_before_wake']+=active&~woke&(a==17)
            env.step(a.contiguous(),active=active)
            stats['turns']+=env.out[:,26]*active;stats['rest_uses']+=env.out[:,34]*active
            for key,col in [('clear',2),('death',6),('timeout',7)]:stats[key]+=env.out[:,col]*active
            assert not (env.out[active,38]>0).any()
            ended=active&(env.out[:,1]>0);read();live=active&~ended
            healed|=live&(state[:,0]>=18);newwake=live&~woke&(state[:,1]>0)
            wake_hp[newwake]=state[newwake,0];woke|=newwake;active&=~ended
        assert not active.any()
        stats['ever_waited_asleep']=(stats['waits_asleep']>0).float()
        stats['rested_before_wake']=(stats['rest_before_wake']>0).float()
        stats['wake_hp']=wake_hp
        arrays={k:v.cpu().numpy().reshape(len(rows),reps) for k,v in stats.items()}
        grouped=[]
        for base in range(0,len(rows),8):
            row={k:rows[base][k] for k in ['geometry','hp','difficulty']}
            for key,a in arrays.items():
                v=a[base:base+8];valid=np.isfinite(v);row[key]=float(v[valid].mean()) if valid.any() else None
            grouped.append(row)
        report['arms'][name+'-'+mode]=grouped;report['wall_seconds']=time.monotonic()-start
        (sr.ROOT/'results/autoregressive-scenario-healing.json').write_text(json.dumps(report,indent=2)+'\n')
        print(name,mode,'clear',float(stats['clear'].mean()),'seconds',round(report['wall_seconds'],1),flush=True)

if __name__=='__main__':main()
