"""Evaluate the fixed seed-0 200M route policy on nested initial enemy subsets."""
import ctypes as C
import json
import pathlib
import subprocess
import time

import torch
from torch.distributions import Distribution
from ablation_storage import Store
from learn_env_ring_multi import Env
from train_clear import Policy
from run_ring_ablations import ROOT, GIB, digest


@torch.no_grad()
def main():
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32=False
    Distribution.set_default_validate_args(False)
    folder=ROOT/'learning-runs/ring-route-cue-corrected-200m-seed0'
    manifest=json.loads((folder/'manifest.json').read_text())
    for source in ('src/learn.cu','src/sim.h'):
        assert digest(ROOT/source)==manifest['sources'][source]
    outdir=ROOT/'results/route-enemy-subsets'
    outdir.mkdir(exist_ok=False)
    store=Store(outdir,GIB,5*GIB)
    store.ensure(128*1024**2)
    lib=outdir/'subset.so'
    subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12',
                    '-shared','-Xcompiler','-fPIC','-DLEARN_ENEMIES=40','-DMULTI_MAP',
                    '-DSLEEP_ON','-DEXPLORE_REWARD','-DEXPLORE_MILLI=2','-DMARK_WALLS',
                    '-DFRONTIER_RING_MEMORY_WALLS_OBS','-DKNOWN_FRONTIER','-DFRONTIER_ROUTE_CUE_OBS',
                    str(ROOT/'src/eval_enemy_subset.cu'),'-o',str(lib)],check=True)
    env=Env(1024,40,corpus=ROOT/'fixtures/d1-corpus-388/validation',map_limit=32,map_filter=-2,library_path=lib)
    p=C.c_void_p
    env.lib.eval_subset.argtypes=[p,C.c_int,p,p,p,p,p]
    checkpoint=folder/'runs/route_cue-seed0/latest.pt'
    saved=torch.load(checkpoint,map_location='cpu',weights_only=False)
    model=Policy(env.obs.shape[1]).cuda(); model.load_state_dict(saved['model']); model.eval()
    store.json('settings.json',dict(checkpoint=str(checkpoint),checkpoint_sha256=digest(checkpoint),
               library_sha256=digest(lib),adapter_sha256=digest(ROOT/'src/eval_enemy_subset.cu'),
               seed=900000,episodes=1024,maps=env.metadata,enemy_counts=[40,32,24,16,8],
               selection='Retain slots 0..count-1 from identical 40-enemy initial states; preserve types and RNG.',
               action_mode='sampled temperature 1',training_seconds=0))
    rows=[]
    for count in [40,32,24,16,8]:
        torch.cuda.synchronize(); start=time.perf_counter()
        env.config[0]=40; env.reset(900000)
        before=env.obs.clone(); mask_before=env.mask.clone()
        env.config[0]=count
        env.check(env.lib.eval_subset(env.state.data_ptr(),env.batch,C.byref(env.config),C.byref(env.tables),env.obs.data_ptr(),env.mask.data_ptr(),env.stream))
        assert torch.equal(before[:,162:162+count*5],env.obs[:,162:162+count*5])
        assert not env.obs[:,162+count*5:362].any()
        assert torch.equal(before[:,362:],env.obs[:,362:])
        assert torch.equal(mask_before,env.mask)
        if count==40: assert torch.equal(before,env.obs)
        torch.manual_seed(900000)
        active=torch.ones(1024,dtype=torch.bool,device='cuda')
        terminal=torch.zeros((1024,8),device='cuda')
        for _ in range(1024):
            dist,_=model(env.obs,env.mask)
            _,out=env.step(dist.sample())
            ended=active&(out[:,1]>.5)
            terminal[ended]=out[ended]; active &= ~ended
        assert not active.any()
        z=terminal.cpu()
        assert (z[:,3]<=count).all()
        assert (z[z[:,2]>.5,3]==count).all()
        def metrics(v):
            return dict(clear_rate=v[:,2].mean().item(),kills=v[:,3].mean().item(),
                        kill_fraction=(v[:,3]/count).mean().item(),death_rate=v[:,6].mean().item(),
                        timeout_rate=v[:,7].mean().item(),turns=v[:,5].mean().item())
        row=dict(enemies=count,evaluation_seconds=time.perf_counter()-start,**metrics(z),
                 maps={str(m['seed']):metrics(z[i::32]) for i,m in enumerate(env.metadata)})
        if count==40:
            reference=json.loads((folder/'runs/route_cue-seed0/result.json').read_text())['final']['sampled']
            for key in ('clear_rate','kills','death_rate','timeout_rate','turns'):
                assert row[key]==reference[key], (key,row[key],reference[key])
        rows.append(row); store.json('summary.json',rows)
        print(json.dumps({k:v for k,v in row.items() if k!='maps'}),flush=True)


if __name__=='__main__': main()
