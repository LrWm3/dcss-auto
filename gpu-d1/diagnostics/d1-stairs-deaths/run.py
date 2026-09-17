"""Exact death replay, legal-action witnesses, and fresh-randomness robustness."""
import ctypes as C
import hashlib
import json
import pathlib
import subprocess
import sys
import time
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/d1-stairs-v2/scripts'))
from common import env,expand_weights
from tactical_models import Policy
from ablation_storage import Store
from assets import FLAGS

HERE=pathlib.Path(__file__).resolve().parent
SUITE=ROOT/'learning-runs/d1-stairs-deaths'
BASE=ROOT/'learning-runs/d1-stairs/adapted.pt'
TACTICAL=ROOT/'learning-runs/autoregressive-survival-balanced/runs/balanced-seed0/latest.pt'
STAGES=['fatal','minus8','minus32','encounter_start','initial']
CONTROLLERS=['base','teacher','tactical']
SEED=950991

def save(store,name,value):store.atomic(name,lambda f:torch.save(value,f),512*1024**2)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def features(obs,mask):
    adj=mask[:,8:16].sum(-1);awake=(obs[:,959:999]<0).sum(-1)
    cells=[(7+dy)*15+7+dx for dx,dy in [(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]]
    walls=(obs[:,cells]<0).sum(-1)
    return torch.stack((obs[:,650]*18,obs[:,651]*2048,adj,awake,walls,mask[:,:8].sum(-1),obs[:,999]*3),-1)

@torch.no_grad()
def capture(model,store):
    ref=json.loads((ROOT/'results/d1-stairs-v2.json').read_text())['confirmation']['adapted']['sampled']
    ids=torch.tensor([i for i,x in enumerate(ref['outcomes']['death']) if x],device='cuda');D=len(ids)
    assert D==58
    e=env('test',3200,SEED);active=torch.ones(3200,device='cuda',dtype=torch.bool)
    terminal=torch.zeros_like(e.out)
    ring={k:torch.empty((33,D,*v.shape[1:]),device='cuda',dtype=v.dtype) for k,v in [('state',e.state),('obs',e.obs),('mask',e.mask)]}
    initial={k:getattr(e,k)[ids].clone() for k in ring};encounter={k:v.clone() for k,v in initial.items()}
    banks={k:torch.empty((5,D,*v.shape[1:]),device='cuda',dtype=v.dtype) for k,v in initial.items()}
    times=torch.zeros(5,D,device='cuda',dtype=torch.long);encounter_t=torch.zeros(D,device='cuda',dtype=torch.long)
    death_t=torch.zeros_like(encounter_t);previous_visible=torch.zeros(D,device='cuda',dtype=torch.bool)
    actions=torch.full((2048,D),-1,device='cuda',dtype=torch.long);trace=torch.zeros(2048,D,7,device='cuda')
    torch.manual_seed(SEED)
    for step in range(2048):
        live=active[ids];visible=e.obs[ids,450:650].reshape(D,40,5)[:,:,4].bool().any(-1)
        starts=live&visible&~previous_visible;encounter_t[starts]=step
        for k in ring:
            now=getattr(e,k)[ids]
            ring[k][step%33]=now
            encounter[k][starts]=now[starts]
        previous_visible=visible;trace[step]=features(e.obs[ids],e.mask[ids])
        a=model(e.obs,e.mask)[0].sample();actions[step,live]=a[ids][live]
        e.step(a,active=active);ended=active&e.out[:,1].bool();terminal[ended]=e.out[ended]
        dead=ended[ids];death_t[dead]=step
        for j,offset in enumerate([0,8,32]):
            t=max(0,step-offset);times[j,dead]=t
            for k in ring:banks[k][j,dead]=ring[k][t%33,dead]
        times[3,dead]=encounter_t[dead]
        for k in ring:
            banks[k][3,dead]=encounter[k][dead];banks[k][4,dead]=initial[k][dead]
        active&=~ended
        if not active.any():break
    assert not active.any()
    for name,col in [('exit',2),('death',6),('timeout',7),('turns',5),('kills',3)]:
        assert terminal[:,col].cpu().tolist()==ref['outcomes'][name],name
    result={k:v.cpu() for k,v in banks.items()}
    result.update(ids=ids.cpu(),times=times.cpu(),death_t=death_t.cpu(),actions=actions.cpu(),trace=trace.cpu(),terminal=terminal[ids].cpu(),maps=[int(m['seed']) for m in e.metadata])
    save(store,'snapshots.pt',result)
    print('Captured all 58 deaths; all 3,200 original outcomes reproduced exactly',flush=True)
    return result

def restore(e,data,index):
    for k in ['state','obs','mask']:getattr(e,k).copy_(data[k].flatten(0,1)[index].to('cuda'))

@torch.no_grad()
def factual_replay(data):
    D=len(data['ids']);N=5*D;e=env('test',N,99);restore(e,data,torch.arange(N))
    active=torch.ones(N,device='cuda',dtype=torch.bool);terminal=torch.zeros_like(e.out)
    starts=data['times'].flatten().cuda();case=torch.arange(N,device='cuda')%D;actions=data['actions'].cuda()
    for step in range(2048):
        a=actions[(starts+step).clamp_max(2047),case];a=torch.where(active,a,16)
        assert ((e.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all()
        e.step(a,active=active);ended=active&e.out[:,1].bool();terminal[ended]=e.out[ended];active&=~ended
        if not active.any():break
    assert not active.any()
    expected=data['terminal'].repeat(5,1).cuda()
    torch.testing.assert_close(terminal,expected,rtol=0,atol=0)
    print('All 290 snapshot replays reproduce the original death and terminal metrics exactly',flush=True)

@torch.no_grad()
def choose(e,models,controller):
    if controller=='teacher':return e.heuristic().clone()
    a=models['base'](e.obs,e.mask)[0].greedy()
    if controller=='tactical':
        combat=(e.obs[:,959:999]<0).any(-1)&~e.mask[:,18].bool()
        a[combat]=models['tactical'](e.obs[combat],e.mask[combat])[0].greedy() if combat.any() else a[combat]
    return a

@torch.no_grad()
def rollout(e,models,controller,first=None,valid=None,record=False):
    active=torch.ones(e.batch,device='cuda',dtype=torch.bool) if valid is None else valid.clone()
    terminal=torch.zeros_like(e.out);first_out=None;trajectory=[]
    for step in range(2048):
        a=first.clone() if step==0 and first is not None else choose(e,models,controller)
        assert ((e.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all()
        if record:trajectory.append(dict(action=int(a[0]),features=features(e.obs,e.mask)[0].cpu().tolist(),position=(e.obs[0,652:654]*torch.tensor([80,70],device='cuda')).round().int().cpu().tolist()))
        e.step(a,active=active)
        if step==0:first_out=e.out.clone()
        ended=active&e.out[:,1].bool();terminal[ended]=e.out[ended];active&=~ended
        if not active.any():break
    assert not active.any()
    return terminal.cpu(),first_out.cpu(),trajectory

@torch.no_grad()
def screen(data,models,store):
    D=len(data['ids']);N=5*D*19;index=torch.arange(5*D).repeat_interleave(19)
    first=torch.arange(19,device='cuda').repeat(5*D)
    results={}
    for controller in CONTROLLERS:
        e=env('test',N,99);restore(e,data,index)
        valid=e.mask.gather(1,first[:,None]).squeeze(1)>0
        default=choose(e,models,controller).cpu()
        print('Screening',controller,int(valid.sum()),'legal branches',flush=True)
        t,one,_=rollout(e,models,controller,first,valid)
        results[controller]=dict(terminal=t.reshape(5,D,19,-1),one=one.reshape(5,D,19,-1),valid=valid.cpu().reshape(5,D,19),default=default.reshape(5,D,19)[:,:,0])
        save(store,'screen.pt',results)
        print(controller,'cases with a successful alternative by stage',[(t.reshape(5,D,19,-1)[j,:,:,2]>0).any(-1).sum().item() for j in range(5)],flush=True)
    return results

def select_witnesses(data,screen):
    selected=[];D=len(data['ids'])
    for i in range(D):
        choice=None
        for stage in range(5):
            for name in CONTROLLERS:
                t=screen[name]['terminal'][stage,i];good=torch.where(t[:,2]>0)[0]
                if len(good):
                    # Prefer later rescue, then the least changed controller.
                    a=int(max(good.tolist(),key=lambda a:(float(t[a,4]),-float(t[a,5]))))
                    choice=dict(case=i,episode=int(data['ids'][i]),stage=stage,controller=name,action=a,
                                original_action=int(data['actions'][int(data['times'][stage,i]),i]),exit_hp=float(t[a,4]),exit_turn=float(t[a,5]));break
            if choice is not None:break
        selected.append(choice)
    return selected

@torch.no_grad()
def robustness(data,models,selected,store):
    # Freeze witnesses selected on the original RNG before these new futures.
    accepted=[x for x in selected if x is not None];K=len(accepted);R=64;N=K*R
    libpath=SUITE/'probe.so'
    if not libpath.exists():
        subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*FLAGS,'-DCLUMP_MODE=0',str(HERE/'probe.cu'),'-o',str(libpath)],check=True)
    probe=C.CDLL(str(libpath));probe.audit_reseed.argtypes=[C.c_void_p,C.c_int,C.c_uint64,C.c_void_p]
    index=torch.tensor([x['stage']*len(data['ids'])+x['case'] for x in accepted]).repeat_interleave(R)
    outputs={}
    for mode in ['base','witness']:
        e=env('test',N,99);restore(e,data,index);e.check(probe.audit_reseed(e.state.data_ptr(),N,981773,e.stream))
        active=torch.ones(N,device='cuda',dtype=torch.bool);terminal=torch.zeros_like(e.out)
        controller_ids=torch.tensor([CONTROLLERS.index(x['controller']) for x in accepted],device='cuda').repeat_interleave(R)
        forced=torch.tensor([x['action'] for x in accepted],device='cuda').repeat_interleave(R)
        for step in range(2048):
            a=choose(e,models,'base')
            if mode=='witness':
                if step==0:a=forced
                else:
                    for cid,name in enumerate(CONTROLLERS[1:],1):
                        if (controller_ids==cid).any():
                            other=choose(e,models,name);a=torch.where(controller_ids==cid,other,a)
            assert ((e.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all()
            e.step(a,active=active);ended=active&e.out[:,1].bool();terminal[ended]=e.out[ended];active&=~ended
            if not active.any():break
        assert not active.any();outputs[mode]=terminal.cpu().reshape(K,R,-1)
        print('Fresh randomness',mode,'exit',float(terminal[:,2].mean()),flush=True)
    save(store,'robustness.pt',dict(selected=accepted,outputs=outputs,repetitions=R,seed=981773))
    return accepted,outputs

def render(obs):
    rows=[];terrain=obs[:225].reshape(15,15);enemy=obs[225:450].reshape(15,15)
    for y in range(15):
        row=''
        for x in range(15):
            c='?' if terrain[y,x]==0 else '#' if terrain[y,x]<0 else '.'
            if enemy[y,x]>0:c='g'
            if y==7 and x==7:c='@'
            row+=c
        rows.append(row)
    return '\n'.join(rows)

@torch.no_grad()
def main():
    torch.set_num_threads(1);SUITE.mkdir(parents=True,exist_ok=True);store=Store(SUITE,4*1024**3,10*1024**3);start=time.monotonic()
    models={'base':Policy('d4_exact',128).cuda().eval()};models['base'].load_state_dict(torch.load(BASE,map_location='cpu',weights_only=False)['model'])
    models['tactical']=expand_weights(torch.load(TACTICAL,map_location='cpu',weights_only=False)['model']).eval()
    manifest=dict(base=str(BASE),base_sha256=digest(BASE),tactical=str(TACTICAL),tactical_sha256=digest(TACTICAL),seed=SEED,stages=STAGES,
                  stages_unit='policy decisions before fatal decision; encounter_start is latest transition into any visible enemy',
                  robustness_rule='64 fresh simulator RNGs; strong practical rescue means >=75% exit and >=20 percentage points better than base greedy from the same state')
    if (SUITE/'manifest.json').exists():
        assert json.loads((SUITE/'manifest.json').read_text())==manifest,'Checkpoint or audit settings changed; use a fresh output directory'
    else:store.json('manifest.json',manifest)
    data=torch.load(SUITE/'snapshots.pt',weights_only=False) if (SUITE/'snapshots.pt').exists() else capture(models['base'],store)
    factual_replay(data)
    s=torch.load(SUITE/'screen.pt',weights_only=False) if (SUITE/'screen.pt').exists() else screen(data,models,store)
    assert set(s)==set(CONTROLLERS)
    selected=select_witnesses(data,s);store.json('witness-selection.json',selected)
    if (SUITE/'robustness.pt').exists():
        r=torch.load(SUITE/'robustness.pt',weights_only=False);accepted,outputs=r['selected'],r['outputs']
    else:accepted,outputs=robustness(data,models,selected,store)
    cases=[];D=len(data['ids'])
    for i in range(D):
        c=dict(case=i,episode=int(data['ids'][i]),map_seed=data['maps'][int(data['ids'][i])%100],death_turn=float(data['terminal'][i,5]),
               kills=float(data['terminal'][i,3]),found_stairs=bool(data['terminal'][i,43]>=0),
               fatal_features=features(data['obs'][0,i:i+1],data['mask'][0,i:i+1])[0].tolist(),fatal_action=int(data['actions'][int(data['death_t'][i]),i]),
               fatal_legal_actions=torch.where(data['mask'][0,i]>0)[0].tolist(),
               immediate_surviving_actions=torch.where(s['base']['valid'][0,i]&~s['base']['one'][0,i,:,6].bool())[0].tolist(),
               witness=selected[i])
        if selected[i] is not None:
            j=next(j for j,x in enumerate(accepted) if x['case']==i)
            b=float(outputs['base'][j,:,2].mean());w=float(outputs['witness'][j,:,2].mean())
            c['fresh_rng']=dict(base_exit=b,witness_exit=w,delta=w-b,strong_rescue=w>=.75 and w-b>=.2)
        cases.append(c)
    by_stage={STAGES[j]:dict(any_witness=int(torch.stack([s[n]['terminal'][j,:,:,2]>0 for n in CONTROLLERS]).any(0).any(-1).sum()),
                controllers={n:int((s[n]['terminal'][j,:,:,2]>0).any(-1).sum()) for n in CONTROLLERS}) for j in range(5)}
    summary=dict(deaths=D,witnesses=sum(x is not None for x in selected),unresolved=sum(x is None for x in selected),
                 fatal_no_legal_action_survives=sum(not x['immediate_surviving_actions'] for x in cases),
                 fresh_rng_strong_rescues=sum(x.get('fresh_rng',{}).get('strong_rescue',False) for x in cases),by_stage=by_stage)
    result=dict(manifest=manifest,summary=summary,cases=cases,wall_seconds=time.monotonic()-start,
                limitations='Witnesses are selected with hindsight on one simulator RNG. A successful exit establishes existence under that simulator state, not an optimal deployable controller. Different actions consume random draws differently. Failed finite searches are unresolved, not proof of unavoidable death. Fresh-RNG comparisons are conditional on selected death snapshots and compare greedy continuations, not overall floor performance.')
    # Save up to six short original/witness traces for inspection, prioritizing robust rescues.
    examples=sorted([x for x in cases if x['witness']],key=lambda c:(-c.get('fresh_rng',{}).get('strong_rescue',False),c['witness']['stage'],c['episode']))[:6]
    for c in examples:
        w=c['witness'];idx=w['stage']*D+c['case'];e=env('test',1,99);restore(e,data,torch.tensor([idx]))
        t,_,trace=rollout(e,models,w['controller'],torch.tensor([w['action']],device='cuda'),record=True)
        assert t[0,2]
        c['example']=dict(start_view=render(data['obs'][w['stage'],c['case']]),rescue_trace=trace,
                          original_start_decision=int(data['times'][w['stage'],c['case']]),
                          original_actions=data['actions'][int(data['times'][w['stage'],c['case']]):int(data['death_t'][c['case']])+1,c['case']].tolist(),
                          original_features=data['trace'][int(data['times'][w['stage'],c['case']]):int(data['death_t'][c['case']])+1,c['case']].tolist())
    store.json('result.json',result);(ROOT/'results/d1-stairs-deaths.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
