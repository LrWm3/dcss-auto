"""Post-selection tactical stat sweeps; fresh simulator verification, no training."""
import fcntl
import json
import time
import torch
import runtime as r

POOL=None
@torch.no_grad()
def futures(model,bank,ids,first,seed):
    global POOL
    if POOL is None:POOL=r.Env('test',batch=2048,seed=211,clump=0,balanced=True)
    e=POOL;n=len(ids);assert n<=2048
    for k in ['state','obs','mask']:getattr(e,k)[:n].copy_(bank[k][ids].cuda())
    e.reseed(seed)
    active=torch.zeros(e.batch,device='cuda',dtype=torch.bool);active[:n]=True
    a=torch.full((e.batch,),16,device='cuda',dtype=torch.long);out=torch.zeros(n,5,device='cuda')
    for tick in range(2048):
        ix=torch.where(active)[0]
        a[ix]=first.cuda() if tick==0 else model(e.obs[ix],e.mask[ix])[0].greedy()
        assert (e.mask[ix].gather(1,a[ix,None])>0).all()
        e.step(a,active=active);ended=active[:n]&e.out[:n,1].bool();out[ended]=e.out[:n][ended][:,[2,6,7,3,49]];active[:n]&=~ended
        if not active.any():break
    assert not active.any() and (out[:,:3].sum(1)==1).all()
    return out.cpu()

@torch.no_grad()
def collect(store):
    file=r.SUITE/'probes/bank.pt'
    if file.exists():return torch.load(file,weights_only=False)
    e=r.Env('test',batch=100,seed=998110,clump=0,balanced=True)
    cases=[i for i in r.SPEC['panels']['main'] if sum(x!=1 for x in r.SPEC['profiles'][i]['code'])<=1 and r.SPEC['profiles'][i]['values'][4]==24]
    bank={k:[] for k in ['state','obs','mask']};rows=[];geometry={}
    for kind,name in enumerate(['corridor','target_selection','sleep_rest']):
        # Geometry is chosen by validity alone, before evaluating any policy.
        e.reset(998110);e.scene(kind,100,0);meta=e.metadata_tensor().cpu()
        picks=torch.where(meta[:,11]>=0)[0][:2];assert len(picks)==2,name
        geometry[name]=[int(meta[i,5]) for i in picks]
        for case in cases:
            for hp in [25,50,100]:
                e.reset(998110);e.scene(kind,hp,case);meta=e.metadata_tensor().cpu()
                assert (meta[picks,11]>=0).all()
                for k in bank:bank[k].append(getattr(e,k)[picks.cuda()].cpu())
                for i in picks.tolist():rows.append(dict(kind=name,profile=case,hp_percent=hp,hp=int(meta[i,2]),max_hp=int(meta[i,3]),map_index=int(meta[i,5]),map_seed=e.metadata[int(meta[i,5])]['seed'],player=int(meta[i,6])))
    result={k:torch.cat(v) for k,v in bank.items()};result.update(rows=rows,geometry=geometry)
    store.atomic('probes/bank.pt',lambda f:torch.save(result,f),128*1024**2)
    return result

@torch.no_grad()
def verify(source,bank,store):
    path=r.SUITE/'probes/verification.json'
    if path.exists():return json.loads(path.read_text())
    n=len(bank['obs']);default=source(bank['obs'].cuda(),bank['mask'].cuda())[0].greedy().cpu()
    scores=torch.full_like(bank['mask'],-1.)
    for start in range(0,n,8):
        ids,actions=torch.where(bank['mask'][start:start+8]>0)
        out=futures(source,bank,(ids+start).repeat_interleave(16),actions.repeat_interleave(16),997100+start)
        scores[ids+start,actions]=out[:,0].reshape(-1,16).mean(1)
    chosen=scores.argmax(1);reports=[]
    # Confirm every selected action and the source action, including apparent ties.
    # No selected action is called better based only on the screening futures.
    for start in range(0,n,32):
        ids=torch.arange(start,min(start+32,n));repeat=ids.repeat_interleave(64)
        base=futures(source,bank,repeat,default[ids].repeat_interleave(64),997500+start)[:,0].reshape(-1,64).mean(1)
        alt=futures(source,bank,repeat,chosen[ids].repeat_interleave(64),997500+start)[:,0].reshape(-1,64).mean(1)
        for i,b,a in zip(ids.tolist(),base.tolist(),alt.tolist()):
            reports.append(dict(state=i,source_action=int(default[i]),screen_best_action=int(chosen[i]),source_exit=b,alternative_exit=a,
                verified_better=bool(chosen[i]!=default[i] and a>=.5 and a-b>=.2)))
    result=dict(screen_futures=16,confirmation_futures=64,reports=reports,screen_scores=scores.tolist(),
        caveat='Best first action under frozen-source greedy continuation, not an optimal policy oracle; thresholds are practical filters.')
    store.json('probes/verification.json',result);return result

@torch.no_grad()
def evaluate(model,bank,name,store):
    path=r.SUITE/f'probes/{name}.json'
    if path.exists():return json.loads(path.read_text())
    d=model(bank['obs'].cuda(),bank['mask'].cuda())[0];actions=d.greedy().cpu();outputs=[]
    for start in range(0,len(actions),32):
        ids=torch.arange(start,min(start+32,len(actions)))
        out=futures(model,bank,ids.repeat_interleave(64),actions[ids].repeat_interleave(64),998500+start)
        outputs.append(out.reshape(len(ids),64,5).mean(1))
    means=torch.cat(outputs);nominal=r.nominal_obs(bank['obs'].cuda());masked=model(nominal,bank['mask'].cuda())[0]
    result=dict(name=name,states=len(actions),futures_per_state=64,mean_exit_rate=float(means[:,0].mean()),rows=[dict(state=i,
        action=int(actions[i]),probabilities=d.probs[i].cpu().tolist(),masked_action=int(masked.greedy()[i]),
        masked_probabilities=masked.probs[i].cpu().tolist(),exit_rate=float(means[i,0]),death_rate=float(means[i,1]),
        timeout_rate=float(means[i,2]),kills=float(means[i,3]),incoming_damage=float(means[i,4])) for i in range(len(actions))])
    store.json(f'probes/{name}.json',result);return result


def main():
    global POOL
    torch.set_num_threads(1);started=time.monotonic()
    lock=(r.SUITE/'.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert (r.SUITE/'result.json').exists(),'Run full-floor selection/evaluations first'
    store=r.Store(r.SUITE,4*1024**3,10*1024**3)
    selection=json.loads((r.SUITE/'selection.json').read_text())
    bank=collect(store);source=r.load_model();verification=verify(source,bank,store)
    paths={'source':r.SOURCE,**{arm:r.SUITE/f'{arm}/checkpoints/{step}.pt' if step else r.SOURCE for arm,step in selection.items()}}
    results={}
    for name,path in paths.items():
        model=r.load_model(path);results[name]=evaluate(model,bank,name,store)
        print(name,results[name]['mean_exit_rate'],flush=True)
    result=dict(schema=1,selection=selection,rows=bank['rows'],geometry=bank['geometry'],verification=verification,models=results,seconds=time.monotonic()-started,
        caveat='Hand-selected geometry types on held-out layouts; two geometry instances per type, not independent evidence from162 layouts. Diagnostic target-selection enemies are heterogeneous and were not part of training.')
    store.json('probes/result.json',result)
    print('complete',result['seconds'],flush=True)

if __name__=='__main__':main()
