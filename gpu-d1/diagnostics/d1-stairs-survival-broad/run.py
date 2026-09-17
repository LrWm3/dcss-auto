"""Broader verified ordinary-map survival examples, with held-out encounters."""
import collections
import ctypes as C
import fcntl
import importlib.util
import json
import pathlib
import signal
import subprocess
import sys
import time

import torch

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('survival_core',ROOT/'diagnostics/d1-stairs-survival/run.py')
core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
from learn_env_ring_multi import Env

SUITE=ROOT/'learning-runs/d1-stairs-survival-broad'
PREVIOUS=ROOT/'learning-runs/d1-stairs-survival'
OFFSETS=[0,2,8,16,32]
POOL={}
START=time.monotonic()


def save(store,name,value):
    store.atomic(name,lambda f:torch.save(value,f),512*1024**2)


def log(store,**kw):
    core.status(store,**kw)


def ordinary(split,batch,seed):
    return Env(batch,24,seed=seed,corpus=core.CORPUS/split,
        map_limit={'train':256,'validation':32,'test':100}[split],map_filter=-1,
        library_path=ROOT/'learning-runs/d1-stairs-assets/stairs-clump0.so')


def probe_library():
    path=SUITE/'probe.so'
    if not path.exists():
        subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12',
            '-shared','-Xcompiler','-fPIC',*core.FLAGS,'-DCLUMP_MODE=0',str(HERE/'probe.cu'),'-o',str(path)],check=True)
    lib=C.CDLL(str(path))
    lib.audit_reseed.argtypes=[C.c_void_p,C.c_int,C.c_uint64,C.c_void_p]
    lib.audit_metadata.argtypes=[C.c_void_p,C.c_int,C.c_void_p,C.c_void_p]
    return lib


@torch.no_grad()
def collect(model,store,probe,split,target,cap,seed,max_steps):
    """Capped deaths per map and balanced early/later deaths; no test maps."""
    name=f'{split}-bank.pt'
    if (SUITE/name).exists():return torch.load(SUITE/name,weights_only=False)
    start=time.monotonic();torch.manual_seed(seed)
    e=ordinary(split,1024,seed)
    ring={k:torch.empty((33,e.batch,*getattr(e,k).shape[1:]),device='cuda',dtype=getattr(e,k).dtype)
          for k in ['state','obs','mask']}
    meta=torch.empty(e.batch,3,device='cuda',dtype=torch.int32)
    starts=torch.zeros(e.batch,device='cuda',dtype=torch.long)
    rows=[];parts={k:[] for k in ring};by_map=collections.Counter();by_age=collections.Counter()
    deaths=0;observed=0;seen=set();episodes=0
    for t in range(max_steps):
        for k in ring:ring[k][t%33]=getattr(e,k)
        e.check(probe.audit_metadata(e.state.data_ptr(),e.batch,meta.data_ptr(),e.stream))
        a=model(e.obs,e.mask)[0].sample();e.step(a)
        ids=torch.where(e.out[:,6]>0)[0];observed+=len(ids);episodes+=int(e.out[:,1].sum())
        selected=[]
        if len(ids):
            records=meta[ids].cpu().tolist();terminal=e.out[ids,5].cpu().tolist()
            for i,(map_id,clumped,episode),turn in zip(ids.tolist(),records,terminal):
                assert clumped==0
                age='early' if turn<=30 else 'later'
                if by_map[map_id]>=cap or by_age[age]>=target//2:continue
                by_map[map_id]+=1;by_age[age]+=1;deaths+=1
                selected.append((i,map_id,episode,turn,age))
            # Deduplicate offsets clamped to the same episode start.
            for offset in OFFSETS:
                chosen=[];times=[]
                for i,map_id,episode,turn,age in selected:
                    when=max(int(starts[i]),t-offset);key=(i,episode,when)
                    if key in seen:continue
                    seen.add(key);chosen.append(i);times.append(when)
                    rows.append(dict(map_index=map_id,map_seed=int(e.metadata[map_id]['seed']),world=i,episode=episode,
                        fatal_collection_step=t,snapshot_collection_step=when,offset=offset,death_turn=turn,age=age))
                if chosen:
                    ix=torch.tensor(chosen,device='cuda');tm=torch.tensor(times,device='cuda')
                    for k in parts:parts[k].append(ring[k][tm%33,ix].cpu())
        starts[e.out[:,1].bool()]=t+1
        if t%512==0:log(store,phase='collecting',split=split,decisions=(t+1)*e.batch,
            retained_deaths=deaths,target=target,maps=len(by_map),early=by_age['early'],later=by_age['later'])
        if deaths>=target or core.STOP:break
    assert deaths>=target//2,(split,deaths,target)
    data={k:torch.cat(v) for k,v in parts.items()}
    # Keep the previous retention distribution fixed; only practice changes.
    old=torch.load(PREVIOUS/'bank.pt',weights_only=False)
    data.update(replay_obs=old['replay_obs'],replay_mask=old['replay_mask'],split=split,rows=rows,
        collection_decisions=(t+1)*e.batch,completed_episodes=episodes,observed_deaths=observed,deaths=deaths,
        by_map=dict(by_map),by_age=dict(by_age),map_seeds=[int(m['seed']) for m in e.metadata],seconds=time.monotonic()-start)
    save(store,name,data)
    assert len(rows)==len(data['obs']) and all(r['map_seed'] in data['map_seeds'] for r in rows)
    log(store,phase='bank_ready',split=split,deaths=deaths,states=len(rows),maps=len(by_map),seconds=data['seconds'])
    return data


@torch.no_grad()
def futures(model,bank,state_ids,actions,seed,probe):
    """Fixed-capacity simulator; infer only active rows to avoid timeout waste."""
    n=len(state_ids);assert 0<n<=2048
    split=bank['split']
    if split not in POOL:POOL[split]=ordinary(split,2048,112)
    e=POOL[split]
    for k in ['state','obs','mask']:getattr(e,k)[:n].copy_(bank[k][state_ids].cuda())
    e.check(probe.audit_reseed(e.state.data_ptr(),n,seed,e.stream))
    active=torch.zeros(e.batch,device='cuda',dtype=torch.bool);active[:n]=True
    terminal=torch.zeros(n,3,device='cuda');a=torch.full((e.batch,),16,device='cuda',dtype=torch.long)
    for t in range(2048):
        ids=torch.where(active)[0]
        a[ids]=actions.cuda() if t==0 else model(e.obs[ids],e.mask[ids])[0].greedy()
        assert (e.mask[ids].gather(1,a[ids,None])>0).all()
        e.step(a,active=active)
        ended=active[:n]&e.out[:n,1].bool();terminal[ended]=e.out[:n][ended][:,[2,6,7]]
        active[:n]&=~ended
        if not active.any():break
    assert not active.any() and (terminal.sum(1)==1).all()
    return terminal.cpu()


@torch.no_grad()
def verify(model,bank,store,probe):
    split=bank['split'];prefix=f'{split}-corrections'
    if (SUITE/f'{prefix}.pt').exists():return torch.load(SUITE/f'{prefix}.pt',weights_only=False)
    started=time.monotonic();N=len(bank['obs'])
    default=torch.cat([model(x.cuda(),m.cuda())[0].greedy().cpu()
        for x,m in zip(bank['obs'].split(512),bank['mask'].split(512))])
    partial=SUITE/f'{split}-screen.pt'
    if partial.exists():
        p=torch.load(partial,weights_only=False);scores=p['scores'];begin=p['next'];seconds=p['seconds']
    else:scores=torch.full_like(bank['mask'],-1.);begin=0;seconds=0.
    elapsed=seconds
    for b in range(begin,N,8):
        ids,acts=torch.where(bank['mask'][b:b+8]>0)
        out=futures(model,bank,(ids+b).repeat_interleave(16),acts.repeat_interleave(16),8100000+b,probe)
        scores[ids+b,acts]=out[:,0].reshape(-1,16).mean(1)
        if (b//8)%16==0 or b+8>=N or core.STOP:
            elapsed=seconds+time.monotonic()-started
            save(store,f'{split}-screen.pt',dict(scores=scores,next=min(b+8,N),seconds=elapsed))
            log(store,phase='screening',split=split,states_done=min(b+8,N),states_total=N,seconds=elapsed,
                estimated_remaining_seconds=elapsed/max(1,min(b+8,N))*(N-min(b+8,N)))
        if core.STOP:return None
    chosen=scores.argmax(1)
    candidate=torch.where((chosen!=default)&(scores.max(1).values-scores.gather(1,default[:,None]).squeeze(1)>=.25))[0]
    store.json(f'{split}-candidates.json',dict(ids=candidate.tolist(),actions=chosen[candidate].tolist(),default=default[candidate].tolist()))
    reports=[];good=[]
    for b in range(0,len(candidate),16):
        ids=candidate[b:b+16];repeated=ids.repeat_interleave(64)
        base=futures(model,bank,repeated,default[ids].repeat_interleave(64),8200000+b,probe)[:,0].reshape(-1,64).mean(1)
        alt=futures(model,bank,repeated,chosen[ids].repeat_interleave(64),8200000+b,probe)[:,0].reshape(-1,64).mean(1)
        for i,bv,av in zip(ids.tolist(),base.tolist(),alt.tolist()):
            accepted=av>=.5 and av-bv>=.2
            reports.append(dict(state=i,map_seed=bank['rows'][i]['map_seed'],base_exit=bv,alternative_exit=av,action=int(chosen[i]),accepted=accepted))
            if accepted:good.append(i)
        log(store,phase='confirming',split=split,candidates_done=min(b+16,len(candidate)),candidates=len(candidate),accepted=len(good))
        if core.STOP:return None
    result=dict(ids=torch.tensor(good,dtype=torch.long),actions=chosen[good],scores=scores,reports=reports,
        seconds=seconds+time.monotonic()-started)
    save(store,f'{prefix}.pt',result)
    store.json(f'{prefix}.json',dict(accepted=len(good),maps=len({bank['rows'][i]['map_seed'] for i in good}),
        candidates=len(candidate),seconds=result['seconds'],reports=reports))
    log(store,phase='verified',split=split,accepted=len(good),maps=len({bank['rows'][i]['map_seed'] for i in good}),seconds=result['seconds'])
    return result


@torch.no_grad()
def diagnostics(model,bank,labels,probe,seed):
    # A fixed random subset limits diagnostics cost, never selected by outcomes.
    g=torch.Generator().manual_seed(seed)
    pick=torch.randperm(len(labels['ids']),generator=g)[:64]
    ids=labels['ids'][pick];y=labels['actions'][pick]
    d=model(bank['obs'][ids].cuda(),bank['mask'][ids].cuda())[0]
    a=d.greedy().cpu();outputs=[]
    for b in range(0,len(ids),32):
        outputs.append(futures(model,bank,ids[b:b+32].repeat_interleave(64),a[b:b+32].repeat_interleave(64),seed+b,probe))
    out=torch.cat(outputs)
    return dict(states=len(ids),state_ids=ids.tolist(),episodes=len(out),exits=int(out[:,0].sum()),
        deaths=int(out[:,1].sum()),timeouts=int(out[:,2].sum()),exit_rate=float(out[:,0].mean()),
        greedy_label_matches=int((a==y).sum()),mean_label_probability=float(d.probs.cpu().gather(1,y[:,None]).mean()),
        per_state_exit=out[:,0].reshape(-1,64).mean(1).tolist(),map_seeds=[bank['rows'][i]['map_seed'] for i in ids.tolist()])


def main():
    torch.set_num_threads(1);SUITE.mkdir(parents=True,exist_ok=True)
    lock=(SUITE/'.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    store=core.Store(SUITE,4*1024**3,10*1024**3)
    def stop(*args):core.STOP=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    manifest=dict(source=str(core.SOURCE),source_sha256=core.digest(core.SOURCE),seed=0,endpoints=core.ENDPOINTS,
        files={str(p):core.digest(p) for p in [pathlib.Path(__file__),HERE/'probe.cu',ROOT/'diagnostics/d1-stairs-survival/run.py',
            ROOT/'diagnostics/d1-stairs-deaths/probe.cu',*core.SCRIPTS.glob('*.py'),ROOT/'branches/d1-stairs-v2/src/learn.cu']},
        libraries={str(p):core.digest(p) for p in (ROOT/'learning-runs/d1-stairs-assets').glob('stairs-clump[01].so')},
        collection=dict(train_target=512,validation_target=128,train_map_cap=4,validation_map_cap=8,
            offsets=OFFSETS,early_later_balance='half <=30 physical turns, half >30',ordinary_placements_only=True),
        verification='16 futures per legal first action; independent64 confirmation >=50% exit, >=20pp improvement; same thresholds as prior run',
        treatment='Same source and5M PPO settings as20-example study; broader practice bank and labels; previous retention buffer unchanged',
        evaluation='Mean sampled/greedy ordinary validation selects endpoint including baseline; challenge encounters excluded from selection; new test seed790021')
    if (SUITE/'manifest.json').exists():assert json.loads((SUITE/'manifest.json').read_text())==manifest,'Source/config drift'
    else:store.json('manifest.json',manifest)
    try:
        model=core.load_model();probe=probe_library()
        bank=collect(model,store,probe,'train',512,4,800110,12288)
        if core.STOP:log(store,phase='stopped');return
        labels=verify(model,bank,store,probe)
        if core.STOP:log(store,phase='stopped');return
        assert len(labels['ids'])>=100,'Too few verified examples to call this a broad follow-up'
        held=collect(model,store,probe,'validation',128,8,800210,8192)
        assert not set(bank['map_seeds'])&set(held['map_seeds'])
        if core.STOP:log(store,phase='stopped');return
        held_labels=verify(model,held,store,probe)
        if core.STOP:log(store,phase='stopped');return
        assert len(held_labels['ids'])>=8
        # Compatibility smoke test: compact active inference preserves a small
        # source rollout against the prior full-batch implementation.
        ids=torch.arange(min(8,len(bank['obs']))).repeat_interleave(2)
        a=model(bank['obs'][ids].cuda(),bank['mask'][ids].cuda())[0].greedy().cpu()
        expected=core.futures(model,bank,ids,a,830110,probe)
        actual=futures(model,bank,ids,a,830110,probe)
        assert torch.equal(expected,actual),'Compact rollout smoke comparison failed'
        store.json('preflight.json',dict(split_disjoint=True,ordinary_only=True,compact_rollout_matches=True,
            training_labels=len(labels['ids']),heldout_labels=len(held_labels['ids'])))
        POOL.clear();torch.cuda.empty_cache();del model
        core.SUITE=SUITE
        curve=core.train('targeted',bank,labels,store,probe)
        if core.STOP:log(store,phase='stopped');return
        previous=json.loads((PREVIOUS/'result.json').read_text());baseline=previous['baseline']
        best=max([dict(decisions=0,**baseline),*curve],key=lambda r:r['sampled']['exit_rate']+r['greedy']['exit_rate'])
        chosen=best['decisions'];store.json('selection.json',dict(decisions=chosen,criterion=manifest['evaluation']))
        paths=dict(baseline=core.SOURCE,previous20=PREVIOUS/'targeted/checkpoints/5000192.pt',
            control=PREVIOUS/'control/checkpoints/5000192.pt',broad=SUITE/f'targeted/checkpoints/{chosen}.pt' if chosen else core.SOURCE)
        model=core.load_model();confirmation={};practice={}
        for name,path in paths.items():
            model.load_state_dict(torch.load(path,map_location='cpu',weights_only=False)['model'])
            confirmation[name]={}
            for mode in ['sampled','greedy']:
                log(store,phase='test_evaluation',model=name,mode=mode)
                confirmation[name][mode]=core.evaluate(model,'test',6400,790021,mode)
                log(store,phase='test_result',model=name,mode=mode,**core.brief(confirmation[name][mode]))
            store.json(f'test-{name}.json',confirmation[name])
            practice[name]={}
            for split,b,l in [('train',bank,labels),('heldout',held,held_labels)]:
                practice[name][split]=diagnostics(model,b,l,probe,840110 if split=='train' else 840210)
                log(store,phase='practice_result',model=name,split=split,exit_rate=practice[name][split]['exit_rate'])
            store.json(f'practice-{name}.json',practice[name])
            POOL.clear();torch.cuda.empty_cache()
        comparisons={ref:{mode:core.paired(confirmation['broad'][mode],confirmation[ref][mode]) for mode in ['sampled','greedy']}
                     for ref in ['baseline','previous20','control']}
        result=dict(manifest=manifest,collection={k:{f:b[f] for f in ['deaths','collection_decisions','completed_episodes','by_map','by_age','seconds']}
            for k,b in [('train',bank),('heldout',held)]},verification={k:dict(examples=len(l['ids']),reports=l['reports'],seconds=l['seconds'])
            for k,l in [('train',labels),('heldout',held_labels)]},curve=curve,selected_decisions=chosen,
            confirmation=confirmation,practice=practice,comparisons=comparisons,wall_seconds=time.monotonic()-START,
            caveat='One training seed; test layouts reused from earlier studies, new placements/RNG. Broader study also changes collection to ordinary placements and balances death timing. Challenge maps are validation maps, never practice resets or supervised labels.')
        store.json('result.json',result)
        (ROOT/'results/d1-stairs-survival-broad.json').write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n')
        log(store,phase='complete',selected_decisions=chosen,comparisons=comparisons,wall_seconds=result['wall_seconds'])
    except Exception as exc:
        log(store,phase='failed',error=repr(exc));raise


if __name__=='__main__':main()
