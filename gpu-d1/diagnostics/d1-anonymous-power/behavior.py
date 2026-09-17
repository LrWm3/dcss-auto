"""Post-training matched power probes and natural-floor timeout interventions."""
import collections
import ctypes as C
import json
import time
import torch
import runtime as r

OUT=r.SUITE/'behavior'
PATHS={'source':r.SOURCE,'500k':r.SUITE/'varied/checkpoints/500224.pt','5m':r.SUITE/'varied/checkpoints/5000192.pt'}

def scene(e,n,profile,hp,kind,adjacent):
    e.check(e.lib.single_scene_api(e.state.data_ptr(),n,C.byref(e.config),C.byref(e.tables),profile,hp,kind,adjacent,e.obs.data_ptr(),e.mask.data_ptr(),e.stream))

@torch.no_grad()
def bank():
    e=r.Env('test',batch=100,seed=812901,clump=0,balanced=True);scene(e,100,0,100,0,0)
    picks=torch.where(e.metadata_tensor()[:,11]>=0)[0][:4];assert len(picks)==4
    initial=e.state[picks].clone();data={k:[] for k in ['state','obs','mask']};rows=[]
    for adjacent in [0,1]:
        for profile in range(9):
            for hp in [50,100]:
                for kind,t in enumerate(r.distribution()['train_templates']):
                    e.state[:4].copy_(initial);scene(e,4,profile,hp,kind,adjacent)
                    meta=e.metadata_tensor()[:4].cpu();assert (meta[:,11]>=0).all() and (meta[:,12]==1).all()
                    records=e.obs[:4,450:650].reshape(4,40,5)
                    assert (records[:,:,4].sum(1)==1).all() and not records[:,:,3].any()
                    for key in data:data[key].append(getattr(e,key)[:4].cpu())
                    for g in range(4):rows.append(dict(context='adjacent' if adjacent else 'sleeping',profile=profile,hp_percent=hp,geometry=g,map_seed=e.metadata[int(meta[g,5])]['seed'],player_hp=int(meta[g,3]),current_hp=int(meta[g,2]),player_damage=int(meta[g,4]),enemy_hp=t['hp'],enemy_damage=t['damage_cap'],category=t['category'],template=kind))
    data={k:torch.cat(v) for k,v in data.items()};data['rows']=rows
    # Holding HP fraction constant, these are the only changing observation
    # fields across player stat pairs. Enemy damage-only pairs change one field.
    for context in ['sleeping','adjacent']:
        for geometry in range(4):
            ids=[i for i,v in enumerate(rows) if v['context']==context and v['geometry']==geometry and v['hp_percent']==100 and v['template']==0]
            x=data['obs'][ids].clone();x[:,1015:1018]=0
            assert torch.equal(x,x[0].expand_as(x))
    lookup={(v['context'],v['profile'],v['hp_percent'],v['geometry'],v['template']):i for i,v in enumerate(rows)}
    for key,i in lookup.items():
        if key[-1] not in [1,4]:continue
        j=lookup[key[:-1]+({1:3,4:5}[key[-1]],)]
        assert torch.where(data['obs'][i]!=data['obs'][j])[0].tolist()==[1019]
        assert torch.equal(data['mask'][i],data['mask'][j])
    return data

@torch.no_grad()
def initial(model,b):
    results=[]
    for start in range(0,len(b['rows']),256):
        x=b['obs'][start:start+256].cuda();mask=b['mask'][start:start+256].cuda();d=model(x,mask)[0];p=d.probs.cpu();a=d.greedy().cpu()
        route=x[:,1006:1014].cpu()
        for j in range(len(p)):
            results.append(dict(state=start+j,action=int(a[j]),move=float(p[j,:8].sum()),attack=float(p[j,8:16].sum()),wait=float(p[j,16]),rest=float(p[j,17]),stair_move=float((p[j,:8]*route[j]).sum()),probs=p[j].tolist()))
    return results

def restore(e,b,ids,seed):
    for key in ['state','obs','mask']:getattr(e,key)[:len(ids)].copy_(b[key][ids].cuda())
    e.reseed(seed)

@torch.no_grad()
def rollouts(e,b,model,mode,repeats=32,seed=99221001):
    rows=[];per=e.batch//repeats
    with torch.random.fork_rng(devices=[0]):
        for start in range(0,len(b['rows']),per):
            ids=torch.arange(start,min(start+per,len(b['rows'])));n=len(ids)*repeats
            restore(e,b,ids.repeat_interleave(repeats),seed+start*repeats);torch.manual_seed(seed+start*repeats)
            active=torch.zeros(e.batch,device='cuda',dtype=torch.bool);active[:n]=True
            actions=torch.full((e.batch,),16,device='cuda',dtype=torch.long);terminal=torch.zeros(n,7,device='cuda')
            counts=torch.zeros(n,6,device='cuda');streak=torch.zeros(n,device='cuda');longest=streak.clone()
            for tick in range(2048):
                ix=torch.where(active)[0];x=e.obs[ix];mask=e.mask[ix]
                awake=(x[:,959:999]<0).any(1)
                if mode=='no_idle_wait':
                    mask=mask.clone();disable=(~awake)&(x[:,650]>=1)&(mask.sum(1)>1);mask[disable,16]=0
                d=model(x,mask)[0];a=d.sample() if mode=='sampled' else d.greedy();actions[ix]=a
                wait=a==16;streak[ix]=torch.where(wait,streak[ix]+1,0);longest[ix]=torch.maximum(longest[ix],streak[ix])
                counts[ix,0]+=a<8;counts[ix,1]+=(a>=8)&(a<16);counts[ix,2]+=wait;counts[ix,3]+=(a==17)
                counts[ix,4]+=wait&(~awake)&(x[:,650]>=1);counts[ix,5]+=1
                e.step(actions,active=active);ended=active[:n]&e.out[:n,1].bool()
                terminal[ended]=e.out[:n][ended][:,[2,6,7,5,3,49,4]];active[:n]&=~ended
                if not active.any():break
            assert not active.any() and (terminal[:,:3].sum(1)==1).all()
            for idx,z,c,long in zip(ids.tolist(),terminal.cpu().reshape(-1,repeats,7),counts.cpu().reshape(-1,repeats,6),longest.cpu().reshape(-1,repeats)):
                row=dict(state=idx,exits=int(z[:,0].sum()),deaths=int(z[:,1].sum()),timeouts=int(z[:,2].sum()),exit_without_kill=int(((z[:,0]>0)&(z[:,4]==0)).sum()),turns=float(z[:,3].mean()),kills=float(z[:,4].mean()),damage=float(z[:,5].mean()),max_wait_streak=float(long.mean()))
                row.update({key:float(c[:,j].mean()) for j,key in enumerate(['move_actions','attack_actions','wait_actions','rest_actions','idle_full_hp_waits','decisions'])});rows.append(row)
    return dict(mode=mode,repeats=repeats,rows=rows)

@torch.no_grad()
def natural_stalls(model):
    # Exactly reproduce the final checkpoint's seen-stat greedy test panel.
    e=r.Env('test',assignments=[p for p in range(9) for _ in range(200)],seed=981011,seed_period=200,map_limit=100,clump=0,balanced=True)
    n=e.batch;active=torch.ones(n,device='cuda',dtype=torch.bool);actions=torch.full((n,),16,device='cuda',dtype=torch.long)
    streak=torch.zeros(n,device='cuda');longest=streak.clone();waits=streak.clone();idle=streak.clone();terminal=torch.zeros_like(e.out)
    captured=torch.zeros(n,device='cuda',dtype=torch.bool);captured_by_profile=[0]*9
    b={k:[] for k in ['state','obs','mask']};rows=[]
    for tick in range(2048):
        ix=torch.where(active)[0];x=e.obs[ix];d=model(x,e.mask[ix])[0];a=d.greedy();actions[ix]=a
        wait=a==16;awake=(x[:,959:999]<0).any(1);streak[ix]=torch.where(wait,streak[ix]+1,0);longest[ix]=torch.maximum(longest[ix],streak[ix]);waits[ix]+=wait;idle[ix]+=wait&(~awake)&(x[:,650]>=1)
        candidates=torch.where(active&(~captured)&(streak>=64))[0].tolist()
        for idx in candidates:
            profile=idx//200;captured[idx]=True
            if captured_by_profile[profile]>=3:continue
            captured_by_profile[profile]+=1
            for key in b:b[key].append(getattr(e,key)[idx:idx+1].cpu())
            obs=e.obs[idx];p=model(obs[None],e.mask[idx:idx+1])[0].probs[0].cpu()
            rows.append(dict(episode=idx,profile=profile,tick_fraction=float(obs[651]),hp_fraction=float(obs[650]),visible_enemies=int(obs[450:650].reshape(40,5)[:,4].sum()),awake_enemies=int((obs[959:999]<0).sum()),adjacent_attack_available=bool(e.mask[idx,8:16].any()),known_stairs=float(obs[999]),probs=p.tolist()))
        e.step(actions,active=active);ended=active&e.out[:,1].bool();terminal[ended]=e.out[ended];active&=~ended
        if not active.any():break
    assert not active.any();t=terminal.cpu();timeout=t[:,7].bool()
    expected=json.loads((r.SUITE/'eval/5000192-test_seen-greedy.json').read_text())
    assert int(t[:,2].sum())==sum(v['exits'] for v in expected['profiles'])
    assert int(t[:,7].sum())==sum(v['timeouts'] for v in expected['profiles'])
    summary=dict(episodes=n,exits=int(t[:,2].sum()),deaths=int(t[:,6].sum()),timeouts=int(timeout.sum()),
        timeout_mean_wait_actions=float(waits.cpu()[timeout].mean()),timeout_mean_idle_full_hp_waits=float(idle.cpu()[timeout].mean()),
        timeout_mean_longest_wait_streak=float(longest.cpu()[timeout].mean()),timeouts_with_64_wait_streak=int((longest.cpu()[timeout]>=64).sum()),captured_by_profile=captured_by_profile,
        timeout_episode_rows=[dict(episode=i,profile=i//200,waits=int(waits[i]),idle_full_hp_waits=int(idle[i]),longest_wait_streak=int(longest[i])) for i in torch.where(timeout)[0].tolist()])
    b={k:torch.cat(v) for k,v in b.items()};b['rows']=rows
    return summary,b

def main():
    torch.set_num_threads(1);OUT.mkdir(exist_ok=True);started=time.monotonic();r.build()
    b=bank();print('matched_bank',len(b['rows']),flush=True)
    report=dict(schema=1,states=b['rows'],initial={},rollouts={},caveats=['Four fixed held-out geometries with nearby visible stairs; not a representative floor distribution.','Bypassing is preferable for the exit objective even when strong. Power sensitivity is not proof of optimal fight/avoid reasoning.','No-idle-WAIT is an evaluation-only action-mask intervention, not a proposed production fix.'])
    e=r.Env('test',batch=2048,seed=181,clump=0,balanced=True)
    for name,path in PATHS.items():
        m=r.load_model(path);report['initial'][name]=initial(m,b)
        for mode in ['greedy','sampled']:
            report['rollouts'][name+'_'+mode]=rollouts(e,b,m,mode)
            print('matched',name,mode,time.monotonic()-started,flush=True)
        (OUT/'partial.json').write_text(json.dumps(report))
    model=r.load_model(PATHS['5m']);natural,stalls=natural_stalls(model)
    report['natural_stalls']=natural;report['stall_states']=stalls['rows'];report['stall_interventions']={}
    torch.save(stalls,OUT/'stalls.pt')
    print('natural',natural['timeouts'],len(stalls['rows']),flush=True)
    for name,mode in [('source','greedy'),('5m','greedy'),('5m','sampled'),('5m','no_idle_wait')]:
        report['stall_interventions'][name+'_'+mode]=rollouts(e,stalls,r.load_model(PATHS[name]),mode,repeats=128,seed=99241001)
        print('intervention',name,mode,time.monotonic()-started,flush=True)
    report['seconds']=time.monotonic()-started
    (OUT/'result.json').write_text(json.dumps(report))
    print('complete',report['seconds'],flush=True)

if __name__=='__main__':main()
