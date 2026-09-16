"""Paired observation interventions on actual, unchanged pocket-defense rollouts."""
import ctypes as C
import importlib.util
import json
import pathlib
import subprocess
import sys
import time
import torch
ROOT=pathlib.Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('pocket',ROOT/'diagnostics/pocket-symmetry/run.py');pocket=importlib.util.module_from_spec(spec);spec.loader.exec_module(pocket)

def main():
    started=time.monotonic();torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
    folder=pathlib.Path(__file__).parent;build=folder/'build';build.mkdir(exist_ok=True)
    pocket.maps(build,6,0)
    flags=['-DPOCKET_DISTANCE=6','-DPOCKET_MIRROR=0','-DCLUMP_MODE=0','-DPROGRESS_INPUT=2','-DKILL_MILLI=1000','-DCLEAR_MILLI=3000','-DDEATH_MILLI=4000','-DFRONTIER_TRAVEL=0','-DOGRE_COUNT=0','-DMONSTER_WAKE_LOS=1','-DTERRAIN_LOS=1','-DGLOBAL_ENEMIES=0','-DLEARN_ENEMIES=40','-DMULTI_MAP','-DSLEEP_ON','-DEXPLORE_REWARD','-DMARK_WALLS','-DEXPLORE_MILLI=2','-DFRONTIER_RING_MEMORY_WALLS_OBS','-DKNOWN_FRONTIER','-DFRONTIER_ROUTE_CUE_OBS','-DFAST_FRONTIER','-DLEARN_BLOCK_SIZE=4','-DCLEAR_PER_ENEMY_MILLI=0']
    lib=build/'probe.so'
    subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*flags,str(ROOT/'diagnostics/pocket-symmetry/probe.cu'),'-o',str(lib)],check=True)
    env=pocket.Env(24*512,24,seed=900000,corpus=build,map_limit=4,library_path=lib)
    p=C.c_void_p;i=C.c_int
    env.lib.hall_init.argtypes=[p,i,p,p,C.c_uint64,p,p,p];env.lib.hall_status.argtypes=[p,i,p,p,p]
    models=[]
    for seed in [0,1,2]:
        for name in ['ordinary','mixed']:
            path=(ROOT/'learning-runs/vision15-seen-death4-30m/runs/tiles_seen_death4-seed0' if name=='ordinary' else ROOT/'learning-runs/vision15-clumps-30m/runs/clumps_third-seed0') if seed==0 else ROOT/'learning-runs/vision15-direction-seeds-30m/runs'/f'{"ordinary" if name=="ordinary" else "clumps_third"}-seed{seed}'
            models.append((f'{name}_seed{seed}',name,path/'snapshots/000030015488.pt','' if seed==0 else f'seed{seed}-noaug-'))
    report=dict(training_performed=False,intervention='Observation only; actual rollouts always use full observation',distance=6,mirror=0,rollouts_per_condition=512,rollout_limit=256,models={},source_hashes={str(q.relative_to(ROOT)):pocket.digest(q) for q in [pathlib.Path(__file__),ROOT/'diagnostics/pocket-symmetry/probe.cu',ROOT/'diagnostics/pocket-symmetry/run.py',ROOT/'branches/vision15-clumps-v1/src/learn.cu']})
    back=torch.tensor([4+(1+(j//512)%4)%4 for j in range(env.batch)],device='cuda')
    grid_keep=torch.tensor([max(abs(x),abs(y))==1 for y in range(-7,8) for x in range(-7,8)],device='cuda')
    group=torch.arange(env.batch,device='cuda')//512
    selected=(group>=16)&(group<20)
    frozen_obs=[];frozen_mask=[];frozen_meta=[]
    for label,name,path,prefix in models:
        model=pocket.Policy().cuda().eval();model.load_state_dict(torch.load(path,map_location='cpu',weights_only=False)['model'])
        env.check(env.lib.hall_init(env.state.data_ptr(),env.batch,C.byref(env.config),C.byref(env.tables),900000,env.obs.data_ptr(),env.mask.data_ptr(),env.stream))
        active=torch.ones(env.batch,dtype=torch.bool,device='cuda');won=torch.zeros_like(active);dead=torch.zeros_like(active)
        status=torch.empty((env.batch,4),dtype=torch.int32,device='cuda');first_seen=torch.zeros_like(active)
        # count, full wait, only-adjacent wait, compacted-adjacent wait, visible others,
        # full greedy-wait, ablated greedy-wait, compacted greedy-wait.
        sums={k:torch.zeros((env.batch,8),device='cuda',dtype=torch.float64) for k in ['all_contact','with_rear','without_rear','high_wait_with_rear','first_contact']}
        removed_total=0;unchanged_without_rear=True
        torch.manual_seed(900000)
        with torch.no_grad():
            for step in range(256):
                if step in [0,2,4,6]:
                    ids=torch.cat([torch.arange(g*512,g*512+16,device='cuda') for g in range(16,20)])
                    frozen_obs.append(env.obs[ids].cpu());frozen_mask.append(env.mask[ids].cpu())
                    frozen_meta.extend([dict(source=label,phase=f'route_{step}',rotation=int(i//512%4),world=int(i%512)) for i in ids.tolist()])
                dist=model(env.obs,env.mask);actions=dist.sample()
                if step<6:actions=back
                env.check(env.lib.hall_status(env.state.data_ptr(),env.batch,actions.data_ptr(),status.data_ptr(),env.stream))
                contact=active&selected&(status[:,0]>0)&(status[:,2]==1)
                take=contact & ~first_seen & (torch.arange(env.batch,device='cuda')%512<64)
                ids=torch.nonzero(take).flatten()
                if len(ids):
                    frozen_obs.append(env.obs[ids].cpu());frozen_mask.append(env.mask[ids].cpu())
                    frozen_meta.extend([dict(source=label,phase='first_contact',rotation=int(i//512%4),world=int(i%512)) for i in ids.tolist()])
                if contact.any():
                    o=env.obs[contact];mask=env.mask[contact];full=dist.probs[contact,8]
                    records=o[:,450:650].reshape(-1,40,5)
                    dx=(records[:,:,0]*80).round();dy=(records[:,:,1]*70).round()
                    present=records[:,:,4]>0
                    adjacent=present&(torch.maximum(dx.abs(),dy.abs())==1)
                    assert (adjacent.sum(1)==1).all()
                    visible=present.sum(1);rear=visible-1
                    assert torch.equal((o[:,225:450]>0).sum(1),visible)
                    adj=o.clone();adj[:,225:450]*=grid_keep
                    adj[:,450:650]=torch.where(adjacent[:,:,None],records,0).flatten(1)
                    assert ((adj[:,225:450]>0).sum(1)==1).all()
                    assert torch.equal(adj[:,:225],o[:,:225]) and torch.equal(adj[:,650:],o[:,650:])
                    assert torch.equal(adj[:,450:650].reshape(-1,40,5)[adjacent],records[adjacent])
                    if (rear==0).any():assert torch.equal(adj[rear==0],o[rear==0])
                    compact=adj.clone();compact[:,450:650]=0;compact[:,450:455]=records[adjacent]
                    no_rear=model(adj,mask).probs[:,8];slot0=model(compact,mask).probs[:,8]
                    # Same inputs, possibly different matmul batch shape: float tolerance.
                    if (rear==0).any():torch.testing.assert_close(full[rear==0],no_rear[rear==0],atol=2e-6,rtol=2e-5)
                    values=torch.stack([torch.ones_like(full),full,no_rear,slot0,rear,full>.5,no_rear>.5,slot0>.5],1).double()
                    ids=torch.nonzero(contact).flatten()
                    filters={'all_contact':torch.ones_like(rear,dtype=torch.bool),'with_rear':rear>0,'without_rear':rear==0,'high_wait_with_rear':(rear>0)&(full>=.5),'first_contact':~first_seen[ids]}
                    for key,keep in filters.items():sums[key][ids]+=values*keep[:,None]
                    first_seen|=contact
                    removed_total+=int(rear.sum())
                env.step(actions,active=active)
                won|=active&(env.out[:,2]>0);dead|=active&(env.out[:,6]>0);active &= env.out[:,1]==0
                if not active.any():break
        reference=json.loads((ROOT/'results'/(prefix+'distant-pocket-6-retreat.json')).read_text())['arms'][name+'_force_route']
        for k,value in [('win',won),('death',dead),('unresolved',active)]:
            assert value.float().reshape(24,512).mean(1).tolist()==reference[k],(label,k,'trajectory changed')
        aggregate={}
        for key,values in sums.items():
            rows=[]
            for rot in range(4):
                batch=values[(16+rot)*512:(17+rot)*512];total=batch.sum(0).cpu().tolist();n=total[0]
                rows.append(dict(pocket_direction=['SE','SW','NW','NE'][rot],contact_states=int(n),episodes=int((batch[:,0]>0).sum()),
                    mean_wait_full=total[1]/n if n else None,mean_wait_adjacent_only=total[2]/n if n else None,mean_wait_adjacent_slot0=total[3]/n if n else None,
                    mean_rear_enemies_visible=total[4]/n if n else None,greedy_wait_full=total[5]/n if n else None,greedy_wait_adjacent_only=total[6]/n if n else None,
                    greedy_wait_adjacent_slot0=total[7]/n if n else None))
            aggregate[key]=rows
        report['models'][label]=dict(checkpoint_sha256=pocket.digest(path),native_trajectory_matches_reference=True,only_enemy_features_changed=True,adjacent_enemy_slot_preserved=True,summary=aggregate)
        report['elapsed_seconds']=time.monotonic()-started
        (ROOT/'results/tactical-next-frozen-capture.json').write_text(json.dumps(report,indent=2)+'\n')
        print(label,'with rear',aggregate['with_rear'],'without rear',aggregate['without_rear'],flush=True)
    bank=dict(obs=torch.cat(frozen_obs),mask=torch.cat(frozen_mask),metadata=frozen_meta)
    destination=ROOT/'learning-runs/tactical-next-assets/frozen.pt';torch.save(bank,destination)
    (ROOT/'results/tactical-next-frozen-bank.json').write_text(json.dumps(dict(states=len(bank['obs']),sha256=pocket.digest(destination),capture_models=list(report['models']),phases=['route_0','route_2','route_4','route_6','first_contact'],training_use=False),indent=2)+'\n')
    print('Frozen bank ready',len(bank['obs']),flush=True)
if __name__=='__main__':main()
