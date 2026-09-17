"""Isolated enemy danger and bypass diagnostics; no training or checkpoint selection."""
import ctypes as C
import json
import pathlib
import subprocess
import time
import torch
import runtime as r

OUT=r.SUITE/'single-enemy'
LIB=OUT/'single.so'
METRICS=['exit','death','timeout','turns','kills','damage','return','hp_first_attack','hp_after_kill','ever_awake']

def build():
    OUT.mkdir(parents=True,exist_ok=True)
    subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*r.FLAGS,'-DCLUMP_MODE=0',str(r.HERE/'single_enemy.cu'),'-o',str(LIB)],check=True)

class Env(r.Env):
    def __init__(self,batch):
        super().__init__('test',batch=batch,seed=812901,clump=0,balanced=True)
        old=self.lib;self.lib=C.CDLL(str(LIB))
        for name,fn in list(old.__dict__.items()):
            if isinstance(fn,C._CFuncPtr):
                new=getattr(self.lib,name);new.argtypes=fn.argtypes;new.restype=fn.restype
        p,i=C.c_void_p,C.c_int
        self.lib.single_scene_api.argtypes=[p,i,p,p,i,i,i,i,p,p,p]
        self.lib.single_rollout_api.argtypes=[p,i,p,p,i,p,p]
    def scene_single(self,n,profile,hp,kind,adjacent):
        self.check(self.lib.single_scene_api(self.state.data_ptr(),n,C.byref(self.config),C.byref(self.tables),profile,hp,kind,adjacent,self.obs.data_ptr(),self.mask.data_ptr(),self.stream))

@torch.no_grad()
def collect(profile_ids=None):
    e=Env(100);e.scene_single(100,0,100,3,0);meta=e.metadata_tensor().cpu()
    picks=torch.where(meta[:,11]>=0)[0][:2];assert len(picks)==2
    initial=e.state[picks.cuda()].clone();bank={k:[] for k in ['state','obs','mask']};rows=[]
    profiles=[p for p in r.SPEC['profiles'] if p['code'] is not None and p['code'][4]==1]
    assert len(profiles)==81
    if profile_ids is not None:profiles=[p for p in profiles if p['id'] in profile_ids]
    for adjacent in [0,1]:
        for profile in profiles:
            for hp in [25,50,100]:
                for kind in range(6):
                    e.state[:2].copy_(initial);e.scene_single(2,profile['id'],hp,kind,adjacent)
                    m=e.metadata_tensor()[:2].cpu();assert (m[:,11]>=0).all()
                    assert (m[:,12]==1).all()
                    records=e.obs[:2,450:650].reshape(2,40,5)
                    assert (records[:,:,4].sum(1)==1).all()
                    assert torch.allclose(records[:,:,2].sum(1)*16,torch.full((2,),float(profile['vector'][3+kind]),device='cuda'))
                    if not adjacent:assert (e.mask[:2,17].bool()==(m[:,2]<m[:,3]).cuda()).all()
                    else:assert not e.mask[:2,17].any()
                    for key in bank:bank[key].append(getattr(e,key)[:2].cpu())
                    for g in range(2):
                        rows.append(dict(context='adjacent_awake' if adjacent else 'sleeping_edge',profile=profile['id'],geometry=g,map_seed=e.metadata[int(m[g,5])]['seed'],player=int(m[g,6]),kind=kind,hp_percent=hp,hp=int(m[g,2]),max_hp=int(m[g,3]),player_damage=int(m[g,4]),enemy_hp=profile['vector'][3+kind],enemy_damage=profile['vector'][9+kind]))
    result={k:torch.cat(v) for k,v in bank.items()};result['rows']=rows
    print('bank',len(rows),'state_bytes',e.state.shape[1],flush=True)
    return result

def restore(e,bank,ids,seed):
    n=len(ids)
    for key in ['state','obs','mask']:getattr(e,key)[:n].copy_(bank[key][ids].cuda())
    e.reseed(seed)

@torch.no_grad()
def controller(e,bank,mode,repeats=256,seed=913701,independent_states=False):
    selected=[i for i,row in enumerate(bank['rows']) if mode==0 or row['context']==('adjacent_awake' if mode==3 else 'sleeping_edge')]
    rows=[];per=e.batch//repeats
    for start in range(0,len(selected),per):
        ids=torch.tensor(selected[start:start+per])
        # The broad descriptive screen shares streams across conditions. For
        # confidence intervals, allocate disjoint streams per canonical state,
        # and reuse that state's streams between controller interventions.
        if independent_states:assert per==1
        restore(e,bank,ids.repeat_interleave(repeats),seed+(int(ids[0])*repeats if independent_states else start))
        out=torch.empty(len(ids)*repeats,10,device='cuda')
        e.check(e.lib.single_rollout_api(e.state.data_ptr(),len(out),C.byref(e.config),C.byref(e.tables),mode,out.data_ptr(),e.stream))
        out=out.cpu().reshape(len(ids),repeats,10)
        assert (out[:,:,:3].sum(2)==1).all()
        if mode==2:assert (out[:,:,0]==1).all() and (out[:,:,4:6]==0).all() and (out[:,:,9]==0).all()
        for idx,samples in zip(ids.tolist(),out):
            means=samples.mean(0);rows.append(dict(state=idx,**{k:float(means[j]) for j,k in enumerate(METRICS)},exits=int(samples[:,0].sum()),deaths=int(samples[:,1].sum())))
    return dict(repeats=repeats,rows=rows)

@torch.no_grad()
def policy(e,bank,model,repeats=64):
    results=[];per=e.batch//repeats
    # Initial decisions and probabilities are evaluated once per actual state.
    initial=[]
    for start in range(0,len(bank['rows']),512):
        d=model(bank['obs'][start:start+512].cuda(),bank['mask'][start:start+512].cuda())[0]
        initial.extend(zip(d.greedy().cpu().tolist(),d.probs.cpu().tolist()))
    for start in range(0,len(bank['rows']),per):
        ids=torch.arange(start,min(start+per,len(bank['rows'])));n=len(ids)*repeats
        restore(e,bank,ids.repeat_interleave(repeats),914901+start)
        active=torch.zeros(e.batch,device='cuda',dtype=torch.bool);active[:n]=True
        a=torch.full((e.batch,),16,device='cuda',dtype=torch.long)
        result=torch.zeros(n,7,device='cuda');returns=torch.zeros(n,device='cuda');rests=torch.zeros(n,device='cuda')
        for step in range(2048):
            ix=torch.where(active)[0];a[ix]=model(e.obs[ix],e.mask[ix])[0].greedy()
            assert (e.mask[ix].gather(1,a[ix,None])>0).all()
            rests[ix]+=(a[ix]==17)
            e.step(a,active=active);returns+=e.out[:n,0]*active[:n]
            ended=active[:n]&e.out[:n,1].bool()
            result[ended]=e.out[:n][ended][:,[2,6,7,5,3,49,0]];active[:n]&=~ended
            if not active.any():break
        assert not active.any();result[:,6]=returns
        values=result.cpu().reshape(len(ids),repeats,7);rest_means=rests.cpu().reshape(len(ids),repeats).mean(1)
        for idx,samples,rest in zip(ids.tolist(),values,rest_means):
            means=samples.mean(0);act,probs=initial[idx]
            results.append(dict(state=idx,**{k:float(means[j]) for j,k in enumerate(METRICS[:7])},rest_actions=float(rest),initial_action=act,initial_probabilities=probs,exits=int(samples[:,0].sum()),deaths=int(samples[:,1].sum())))
    return dict(repeats=repeats,rows=results)

def main():
    torch.set_num_threads(1);started=time.monotonic();build();bank=collect()
    e=Env(2048);report=dict(schema=1,states=bank['rows'],profiles=r.SPEC['profiles'],metrics=METRICS,controllers={},models={},
        design='All 81 combat-stat grid combinations at count=24, six enemy kinds, 25/50/100% HP, two held-out map geometries. Exactly one living enemy. Sleeping distance7 with three visible safe stairs; paired adjacent-awake variant. Geometry selected by feasibility alone.',
        caveats=['Engineered nearby exits: safe bypass is always preferable for exit reward; this is not a test of necessary fighting or power-dependent optimal strategy reversal.','Only two geometries; futures measure combat randomness, not independent map/training-seed uncertainty.','Fight controller approaches sleeper then waits for adjacency and attacks; heal-first uses the existing REST macro then the same controller.','Controller pathfinding uses static distance fields to approach the initially visible sleeper, and observed safe floor for exits. Models retain their normal partial observations and greedy actions.'])
    for mode,name in enumerate(['fight','heal_then_fight','bypass']):
        report['controllers'][name]=controller(e,bank,mode)
        (OUT/'result.partial.json').write_text(json.dumps(report))
        print(name,'exit',sum(x['exit'] for x in report['controllers'][name]['rows'])/len(report['controllers'][name]['rows']),'seconds',time.monotonic()-started,flush=True)
    selection=json.loads((r.SUITE/'selection.json').read_text())
    for name,path in {'source':r.SOURCE,**{arm:r.SUITE/f'{arm}/checkpoints/{step}.pt' if step else r.SOURCE for arm,step in selection.items()}}.items():
        report['models'][name]=policy(e,bank,r.load_model(path))
        (OUT/'result.partial.json').write_text(json.dumps(report))
        print(name,'exit',sum(x['exit'] for x in report['models'][name]['rows'])/len(bank['rows']),'seconds',time.monotonic()-started,flush=True)
    report['seconds']=time.monotonic()-started
    (OUT/'result.json').write_text(json.dumps(report))
    print('complete',report['seconds'],flush=True)

if __name__=='__main__':main()
