"""Two matched PPO continuations and locked held-out stat/layout evaluation."""
import copy
import fcntl
import json
import math
import signal
import time
import torch
import runtime as r

ENDPOINTS=[1000448,3000320,5000192]
STOP=False
START=time.monotonic()

def log(store,**kw):
    store.json('status.json',dict(updated_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),**kw));print(kw,flush=True)

def save(store,name,value):store.atomic(name,lambda f:torch.save(value,f),256*1024**2)

@torch.no_grad()
def evaluate(model,cases,split='validation',maps=32,repeats=2,mode='sampled',seed=991101,mask_stats=False):
    started=time.monotonic();period=maps*repeats
    e=r.Env(split,assignments=[c for c in cases for _ in range(period)],seed=seed,seed_period=period,map_limit=maps,clump=0,balanced=True)
    n=e.batch;active=torch.ones(n,device='cuda',dtype=torch.bool);terminal=torch.zeros_like(e.out)
    rewards=torch.zeros(n,device='cuda');actions=torch.full((n,),16,device='cuda',dtype=torch.long)
    rest_turns=torch.zeros(n,device='cuda');decisions=torch.zeros(n,device='cuda')
    with torch.random.fork_rng(devices=[0]):
        torch.manual_seed(seed)
        for _ in range(2048):
            ids=torch.where(active)[0];x=e.obs[ids]
            if mask_stats:x=r.nominal_obs(x)
            d=model(x,e.mask[ids])[0];a=d.greedy() if mode=='greedy' else d.sample();actions[ids]=a
            assert (e.mask[ids].gather(1,a[:,None])>0).all()
            e.step(actions,active=active);rewards[ids]+=e.out[ids,40];decisions[ids]+=1
            rest_turns[ids]+=(a==17)*e.out[ids,26]
            ended=active&e.out[:,1].bool();terminal[ended]=e.out[ended];active &= ~ended
            if not active.any():break
    assert not active.any()
    torch.testing.assert_close(rewards,terminal[:,2]-.00001*terminal[:,5],atol=1e-4,rtol=0)
    assert ((terminal[:,2]+terminal[:,6]+terminal[:,7])==1).all()
    assert torch.equal(terminal[:,45].long(),e.assignment_tensor.long())
    t=terminal.cpu();rt=rest_turns.cpu();de=decisions.cpu();rows=[]
    def mean(x):return float(x.float().mean()) if len(x) else None
    for j,case in enumerate(cases):
        sl=slice(j*period,(j+1)*period);z=t[sl];success=z[:,2]>0;found=z[:,43]>=0
        rows.append(dict(profile=case,episodes=period,exits=int(z[:,2].sum()),deaths=int(z[:,6].sum()),timeouts=int(z[:,7].sum()),
            exit_rate=mean(z[:,2]),turns=mean(z[:,5]),rest_turns=mean(rt[sl]),decisions=mean(de[sl]),
            discovery_rate=mean(found),first_discovery_turn=mean(z[found,43]),post_discovery_turns=mean(z[success,5]-z[success,43]),
            alive_fraction_on_exit=mean((z[success,48]-z[success,3])/z[success,48]),
            incoming_damage=mean(z[:,49]),enemy_attacks=mean(z[:,50]),enemy_blocks=mean(z[:,51]),enemy_dodges=mean(z[:,52]),
            exits_by_map=z[:,2].reshape(repeats,maps).sum(0).int().tolist(),deaths_by_map=z[:,6].reshape(repeats,maps).sum(0).int().tolist(),
            timeouts_by_map=z[:,7].reshape(repeats,maps).sum(0).int().tolist()))
    return dict(split=split,seed=seed,mode=mode,masked_stats=mask_stats,episodes=n,maps=[m['seed'] for m in e.metadata],repeats=repeats,
        exit_rate=mean(t[:,2]),death_rate=mean(t[:,6]),timeout_rate=mean(t[:,7]),turns=mean(t[:,5]),seconds=time.monotonic()-started,profiles=rows)


def brief(x):return {k:x[k] for k in ['exit_rate','death_rate','timeout_rate','turns','seconds']}

def validation(model,store,arm,decisions):
    rows={}
    for mode in ['sampled','greedy']:
        path=r.SUITE/f'{arm}/validation-{decisions}-{mode}.json'
        if path.exists():rows[mode]=json.loads(path.read_text())
        else:
            rows[mode]=evaluate(model,r.SPEC['panels']['validation'],mode=mode)
            store.json(str(path.relative_to(r.SUITE)),rows[mode])
        log(store,phase='validation',arm=arm,decisions=decisions,mode=mode,**brief(rows[mode]))
    return rows


def train(arm,store):
    torch.manual_seed(0);model=r.load_model();reference=copy.deepcopy(model).requires_grad_(False);anchor=r.ReplayAnchor(reference)
    optimizer=torch.optim.Adam(model.parameters(),lr=.0003,eps=1e-5)
    e=r.Env(batch=512,seed=0,varied=arm=='varied')
    total=0;seconds=0.;turns=0;history=[]
    hist=torch.zeros(195,device='cuda',dtype=torch.long)
    latest=r.SUITE/arm/'latest.pt'
    if latest.exists():
        c=torch.load(latest,map_location='cpu',weights_only=False);model.load_state_dict(c['model']);optimizer.load_state_dict(c['optimizer'])
        for k in ['state','obs','mask']:getattr(e,k).copy_(c[k])
        total=c['decisions'];seconds=c['training_seconds'];turns=c['physical_turns'];history=c['history'];hist.copy_(c['episode_histogram'])
        torch.set_rng_state(c['rng']);torch.cuda.set_rng_state(c['cuda_rng'])
    def persist():save(store,f'{arm}/latest.pt',dict(schema=1,model=r.weights(model),optimizer=optimizer.state_dict(),decisions=total,
        training_seconds=seconds,physical_turns=turns,history=history,episode_histogram=hist.cpu(),
        **{k:getattr(e,k).cpu() for k in ['state','obs','mask']},rng=torch.get_rng_state(),cuda_rng=torch.cuda.get_rng_state()))
    obs=torch.empty(64,512,r.OBS,device='cuda');mask=torch.empty(64,512,19,device='cuda')
    actions=torch.empty(64,512,device='cuda',dtype=torch.long)
    lp,val,rew,done,adv=[torch.empty(64,512,device='cuda') for _ in range(5)]
    while total<ENDPOINTS[-1] and not STOP:
        endpoint=min(x for x in ENDPOINTS if x>total);T=min(64,math.ceil((endpoint-total)/512))
        torch.cuda.synchronize();started=time.monotonic();physical=torch.zeros((),device='cuda')
        with torch.no_grad():
            for t in range(T):
                obs[t]=e.obs;mask[t]=e.mask;d,v=model(e.obs,e.mask);a=d.sample()
                actions[t]=a;lp[t]=d.log_prob(a);val[t]=v;e.step(a)
                rew[t]=e.out[:,40];done[t]=e.out[:,1];physical+=e.out[:,26].sum()
                hist.scatter_add_(0,e.out[:,45].long(),e.out[:,1].long())
            nv=model(e.obs,e.mask)[1];gae=torch.zeros(512,device='cuda')
            for t in reversed(range(T)):
                live=1-done[t];delta=rew[t]+live*nv-val[t]
                gae=delta+.95*live*gae;adv[t]=gae;nv=val[t]
            returns=(val[:T]+adv[:T]).flatten();advantages=adv[:T].flatten();advantages=(advantages-advantages.mean())/(advantages.std()+1e-8)
        x=obs[:T].flatten(0,1);m=mask[:T].flatten(0,1)
        for _ in range(4):
            for ix in torch.randperm(T*512,device='cuda').split(4096):
                d,v=model(x[ix],m[ix]);ratio=(d.log_prob(actions[:T].flatten()[ix])-lp[:T].flatten()[ix]).exp()
                pg=-torch.minimum(ratio*advantages[ix],ratio.clamp(.8,1.2)*advantages[ix]).mean()
                loss=pg+.25*(v-returns[ix]).square().mean()+anchor.loss(model)
                assert torch.isfinite(loss)
                optimizer.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),.5);optimizer.step()
        torch.cuda.synchronize();seconds+=time.monotonic()-started;turns+=int(physical);total+=T*512
        if total==endpoint:
            save(store,f'{arm}/checkpoints/{total}.pt',dict(model=r.weights(model),decisions=total,schema=1))
            row=dict(decisions=total,training_seconds=seconds,physical_turns=turns,episode_histogram=hist.cpu().tolist())
            row.update(validation(model,store,arm,total));history.append(row);store.json(f'{arm}/curve.json',history);persist()
        elif total%327680==0:
            persist();log(store,phase='training',arm=arm,decisions=total,training_seconds=seconds,
                estimated_remaining_training_seconds=seconds/total*(ENDPOINTS[-1]-total))
    persist();return history


def main():
    global STOP
    torch.set_num_threads(1);r.SUITE.mkdir(parents=True,exist_ok=True)
    lock=(r.SUITE/'.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    store=r.Store(r.SUITE,4*1024**3,10*1024**3)
    def stop(*args):
        global STOP
        STOP=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    pre=json.loads((r.SUITE/'preflight.json').read_text())
    assert all(r.digest(p)==v for p,v in pre['files'].items()),'Re-run preflight after source changes'
    manifest=dict(schema=1,source=str(r.SOURCE),source_sha256=r.digest(r.SOURCE),profiles=r.SPEC,endpoints=ENDPOINTS,
        source_files={str(p):r.digest(p) for p in [r.HERE/'runtime.py',r.HERE/'run.py',r.HERE/'preflight.py',r.HERE/'learn.cu',r.HERE/'hooks.cu',*r.OLD.glob('*.py')]},
        libraries={str(p):r.digest(p) for p in r.SUITE.glob('stats-clump*.so')},
        seed=0,nominal_spawn_protocol='new independent stairs and40-position prefix deck',
        training='matched ordinary PPO; replay-only nominal anchors; no corrective labels or practice resets',
        selection='mean config exit rate across sampled/greedy validation; source eligible')
    if (r.SUITE/'manifest.json').exists():assert json.loads((r.SUITE/'manifest.json').read_text())==manifest,'Source drift'
    else:store.json('manifest.json',manifest)
    try:
        model=r.load_model();baseline=validation(model,store,'source',0);del model
        curves={}
        for arm in ['fixed','varied']:
            curves[arm]=train(arm,store)
            if STOP:log(store,phase='stopped');return
            torch.cuda.empty_cache()
        choices={}
        for arm,curve in curves.items():
            best=max([dict(decisions=0,**baseline),*curve],key=lambda x:x['sampled']['exit_rate']+x['greedy']['exit_rate'])
            choices[arm]=best['decisions']
        store.json('selection.json',choices);log(store,phase='selection',choices=choices)
        # Selection is frozen before opening any final test panel.
        paths={'source':r.SOURCE,**{arm:r.SUITE/f'{arm}/checkpoints/{step}.pt' if step else r.SOURCE for arm,step in choices.items()}}
        panels=[('main','test',100),('main','train',32),('interpolation','test',100),('extrapolation','test',100)]
        for name,path in paths.items():
            model=r.load_model(path)
            for panel,split,maps in panels:
                for mode in ['sampled','greedy']:
                    file=f'eval/{name}-{panel}-{split}-{mode}.json'
                    if (r.SUITE/file).exists():continue
                    log(store,phase='test_evaluation',model=name,panel=panel,split=split,mode=mode)
                    result=evaluate(model,r.SPEC['panels'][panel],split,maps,2,mode,992101 if panel=='main' else 992201)
                    store.json(file,result);log(store,phase='test_result',model=name,panel=panel,split=split,mode=mode,**brief(result))
            del model;torch.cuda.empty_cache()
        # Diagnostic intervention: actual mechanics held fixed, appended stats replaced.
        model=r.load_model(paths['varied'])
        for mode in ['sampled','greedy']:
            file=f'eval/varied-masked-main-test-{mode}.json'
            if not (r.SUITE/file).exists():
                result=evaluate(model,r.SPEC['panels']['main'],'test',100,2,mode,992101,True);store.json(file,result)
                log(store,phase='masked_stats_result',mode=mode,**brief(result))
        store.json('result.json',dict(manifest=manifest,selection=choices,curve_paths={k:f'{k}/curve.json' for k in curves},wall_seconds=time.monotonic()-START))
        log(store,phase='main_complete',selection=choices,wall_seconds=time.monotonic()-START)
    except Exception as exc:log(store,phase='failed',error=repr(exc));raise

if __name__=='__main__':main()
