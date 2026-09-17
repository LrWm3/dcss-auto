"""Train-only death-state practice, paired ordinary PPO control, held-out exits."""
import copy
import ctypes as C
import fcntl
import hashlib
import importlib.util
import json
import math
import pathlib
import signal
import subprocess
import sys
import time

import numpy as np
import torch

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'branches/d1-stairs-v2/scripts'
sys.path.insert(0, str(SCRIPTS))
from common import env, weights, NavigationAnchor, CORPUS
from evaluate import evaluate
from tactical_models import Policy
from ablation_storage import Store
from assets import FLAGS

HERE = pathlib.Path(__file__).resolve().parent
SUITE = ROOT / 'learning-runs/d1-stairs-survival'
SOURCE = ROOT / 'learning-runs/d1-stairs/adapted.pt'
ENDPOINTS = [500224, 1000448, 3000320, 5000192]
MIB = 1024 ** 2
STOP = False


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(store, name, value):
    store.atomic(name, lambda f: torch.save(value, f), 256 * MIB)


def status(store, **kw):
    store.json('status.json', dict(updated_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **kw))
    print(kw, flush=True)


def load_model():
    m = Policy('d4_exact', 128).cuda().eval()
    m.load_state_dict(torch.load(SOURCE, map_location='cpu', weights_only=False)['model'])
    return m


def reseeder():
    p = SUITE / 'probe.so'
    if not p.exists():
        subprocess.run(['nvcc', '-O3', '-std=c++17', '-arch=sm_75', '-ccbin', '/usr/bin/g++-12',
                        '-shared', '-Xcompiler', '-fPIC', *FLAGS, '-DCLUMP_MODE=1',
                        str(ROOT / 'diagnostics/d1-stairs-deaths/probe.cu'), '-o', str(p)], check=True)
    lib = C.CDLL(str(p))
    lib.audit_reseed.argtypes = [C.c_void_p, C.c_int, C.c_uint64, C.c_void_p]
    return lib


@torch.no_grad()
def collect(model, store):
    """Ordinary training worlds, sampled source; save -8/-32 states per death."""
    start = time.monotonic()
    e = env('train', 1024, 720110)
    torch.manual_seed(720110)
    rings = {k: torch.empty((33, e.batch, *getattr(e, k).shape[1:]), device='cuda',
                           dtype=getattr(e, k).dtype) for k in ['state', 'obs', 'mask']}
    bank = {k: [] for k in rings}
    starts = torch.zeros(e.batch, device='cuda', dtype=torch.long)
    replay_x, replay_m = [], []
    death_rows = []
    deaths = 0
    for t in range(2048):
        for k in rings:
            rings[k][t % 33] = getattr(e, k)
        if t % 4 == 0 and len(replay_x) < 256:
            ix = torch.randperm(e.batch, device='cuda')[:128]
            replay_x.append(e.obs[ix].cpu()); replay_m.append(e.mask[ix].cpu())
        a = model(e.obs, e.mask)[0].sample()
        e.step(a)
        ids = torch.where(e.out[:,6] > 0)[0][:max(0, 96-deaths)]
        if len(ids):
            # An episode can die before 32 decisions; never cross its reset.
            for offset in [8, 32]:
                when = torch.maximum(starts[ids], torch.full_like(ids, t-offset))
                for k in bank:
                    bank[k].append(rings[k][when % 33, ids].cpu())
                death_rows.extend(dict(world=int(i), fatal_collection_step=t, snapshot_collection_step=int(w),
                                       offset=offset, death_turn=float(e.out[i,5])) for i,w in zip(ids.tolist(),when.tolist()))
            deaths += len(ids)
        starts[e.out[:,1].bool()] = t+1
        if deaths >= 96:
            break
    assert deaths >= 16, 'Insufficient training deaths for practice'
    result = {k: torch.cat(v) for k,v in bank.items()}
    result.update(replay_obs=torch.cat(replay_x), replay_mask=torch.cat(replay_m), rows=death_rows,
                  collection_decisions=(t+1)*e.batch, deaths=deaths, seconds=time.monotonic()-start)
    save(store, 'bank.pt', result)
    status(store, phase='bank_collected', deaths=deaths, states=len(result['obs']), seconds=result['seconds'])
    return result


@torch.no_grad()
def futures(model, bank, state_ids, actions, seed, probe):
    """Full exits from fixed scenes; one forced action then unchanged greedy source."""
    e = env('train', len(state_ids), 110)
    for k in ['state','obs','mask']:
        getattr(e,k).copy_(bank[k][state_ids].cuda())
    e.check(probe.audit_reseed(e.state.data_ptr(), e.batch, seed, e.stream))
    active = torch.ones(e.batch, device='cuda', dtype=torch.bool)
    terminal = torch.zeros(e.batch, 3, device='cuda')
    for t in range(2048):
        a = actions.cuda() if t == 0 else model(e.obs,e.mask)[0].greedy()
        assert ((e.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all()
        e.step(a,active=active)
        ended = active & e.out[:,1].bool()
        terminal[ended] = e.out[ended][:,[2,6,7]]
        active &= ~ended
        if not active.any():
            break
    assert not active.any()
    assert (terminal.sum(1)==1).all()
    return terminal.cpu()


@torch.no_grad()
def corrections(model, bank, store, probe):
    start = time.monotonic()
    default = model(bank['obs'].cuda(), bank['mask'].cuda())[0].greedy().cpu()
    scores = torch.full_like(bank['mask'], -1.)
    # Screen 16 futures per legal action, at most 2,432 worlds per batch.
    for begin in range(0,len(default),8):
        ids, acts = torch.where(bank['mask'][begin:begin+8] > 0)
        out = futures(model,bank,(ids+begin).repeat_interleave(16),acts.repeat_interleave(16),721000+begin,probe)
        scores[ids+begin,acts] = out[:,0].reshape(-1,16).mean(1)
        status(store,phase='screening_actions',states_done=min(begin+8,len(default)),states_total=len(default))
    chosen = scores.argmax(1)
    candidates = torch.where((chosen!=default)&(scores.max(1).values-scores.gather(1,default[:,None]).squeeze(1)>=.25))[0]
    store.json('candidates.json',dict(ids=candidates.tolist(),actions=chosen[candidates].tolist(),
                                    default=default[candidates].tolist(),screen_repeats=16))
    # Selection above is frozen before independent confirmation randomness.
    good, reports = [], []
    for begin in range(0,len(candidates),16):
        ids = candidates[begin:begin+16]
        repeated = ids.repeat_interleave(64)
        b = futures(model,bank,repeated,default[ids].repeat_interleave(64),731000+begin,probe)[:,0].reshape(-1,64).mean(1)
        w = futures(model,bank,repeated,chosen[ids].repeat_interleave(64),731000+begin,probe)[:,0].reshape(-1,64).mean(1)
        for i,bv,wv in zip(ids.tolist(),b.tolist(),w.tolist()):
            accepted = wv>=.5 and wv-bv>=.2
            reports.append(dict(state=i,base_exit=bv,alternative_exit=wv,action=int(chosen[i]),accepted=accepted))
            if accepted:good.append(i)
    assert len(good)>=4, f'Only {len(good)} reliable corrections; inspect preparation before training'
    result=dict(ids=torch.tensor(good),actions=chosen[good],scores=scores,reports=reports,
                seconds=time.monotonic()-start)
    save(store,'corrections.pt',result)
    store.json('corrections.json',dict(accepted=len(good),candidate_count=len(candidates),reports=reports,seconds=result['seconds']))
    status(store,phase='corrections_ready',accepted=len(good),candidates=len(candidates),seconds=result['seconds'])
    return result


def brief(r):
    return {k:r[k] for k in ['exit_rate','death_rate','timeout_rate','turns']}


def train(arm, bank, correction, store, probe):
    global STOP
    torch.manual_seed(0)
    model = load_model(); reference = copy.deepcopy(model).requires_grad_(False)
    anchor = NavigationAnchor()
    optimizer = torch.optim.Adam(model.parameters(),lr=.0003,eps=1e-5)
    e = env('train',512,0)
    b = {k:bank[k].cuda() for k in ['state','obs','mask']}
    rx,rm = bank['replay_obs'].cuda(),bank['replay_mask'].cuda()
    ci = correction['ids'].cuda();cx,cm,cy = b['obs'][ci],b['mask'][ci],correction['actions'].cuda()
    with torch.no_grad():
        rp = torch.cat([reference(x,m)[0].probs for x,m in zip(rx.split(1024),rm.split(1024))])
    total=0;seconds=0.;turns=0;practice_decisions=0;history=[]
    latest=SUITE/arm/'latest.pt'
    def refill(ids):
        if not len(ids):return
        ix=torch.randint(len(b['obs']),(len(ids),),device='cuda')
        for k in b:getattr(e,k)[ids]=b[k][ix]
        # Reseed a temporary contiguous state buffer, then write it back.
        tmp=e.state[ids].contiguous()
        seed=int(torch.randint(1,2**31,(),device='cpu'))
        e.check(probe.audit_reseed(tmp.data_ptr(),len(ids),seed,e.stream));e.state[ids]=tmp
    if latest.exists():
        c=torch.load(latest,map_location='cpu',weights_only=False)
        model.load_state_dict(c['model']);optimizer.load_state_dict(c['optimizer'])
        for k in b:getattr(e,k).copy_(c[k])
        total=c['decisions'];seconds=c['seconds'];turns=c['turns'];practice_decisions=c['practice_decisions'];history=c['history']
        torch.set_rng_state(c['rng']);torch.cuda.set_rng_state(c['cuda_rng'])
    elif arm=='targeted':refill(torch.arange(384,512,device='cuda'))
    def persist():
        save(store,f'{arm}/latest.pt',dict(model=weights(model),optimizer=optimizer.state_dict(),decisions=total,
            seconds=seconds,turns=turns,practice_decisions=practice_decisions,history=history,
            **{k:getattr(e,k).cpu() for k in b},rng=torch.get_rng_state(),cuda_rng=torch.cuda.get_rng_state()))
    obs=torch.empty(64,512,1015,device='cuda');mask=torch.empty(64,512,19,device='cuda')
    actions=torch.empty(64,512,device='cuda',dtype=torch.long)
    lp,val,rew,done,adv=[torch.empty(64,512,device='cuda') for _ in range(5)]
    while total<ENDPOINTS[-1] and not STOP:
        endpoint=min(x for x in ENDPOINTS if x>total);T=min(64,math.ceil((endpoint-total)/512))
        torch.cuda.synchronize();start=time.monotonic();physical=torch.zeros((),device='cuda')
        with torch.no_grad():
            for t in range(T):
                obs[t]=e.obs;mask[t]=e.mask;d,v=model(e.obs,e.mask);a=d.sample()
                actions[t]=a;lp[t]=d.log_prob(a);val[t]=v;e.step(a)
                rew[t]=e.out[:,40];done[t]=e.out[:,1];physical+=e.out[:,26].sum()
                if arm=='targeted':refill(torch.where(e.out[384:,1]>0)[0]+384)
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
                ri=torch.randint(len(rx),(256,),device='cuda');p=model(rx[ri],rm[ri])[0].probs
                kl=(rp[ri]*(rp[ri].clamp_min(1e-30).log()-p.clamp_min(1e-30).log())).sum(-1).mean()
                loss=pg+.25*(v-returns[ix]).square().mean()+anchor.loss(model,x[ix],m[ix])+.5*kl
                if arm=='targeted':
                    ids=torch.randint(len(cx),(128,),device='cuda')
                    loss+=.5*(-model(cx[ids],cm[ids])[0].log_prob(cy[ids]).mean())
                assert torch.isfinite(loss)
                optimizer.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),.5);optimizer.step()
        torch.cuda.synchronize();seconds+=time.monotonic()-start;turns+=int(physical);total+=T*512
        practice_decisions+=T*128 if arm=='targeted' else 0
        if total==endpoint:
            row=dict(decisions=total,training_seconds=seconds,physical_turns=turns,practice_decisions=practice_decisions)
            for mode in ['sampled','greedy']:
                row[mode]=evaluate(model,mode=mode)
                status(store,phase='validation',arm=arm,decisions=total,mode=mode,**brief(row[mode]))
            history.append(row);store.json(f'{arm}/curve.json',history)
            save(store,f'{arm}/checkpoints/{total}.pt',dict(model=weights(model),decisions=total))
            persist()
        elif total%327680==0:
            persist();status(store,phase='training',arm=arm,decisions=total,training_seconds=seconds,
                             estimated_remaining_training_seconds=seconds/total*(ENDPOINTS[-1]-total))
    persist()
    return history


def paired(a,b):
    n=len(a['maps']);delta=np.array(a['outcomes']['exit'])-np.array(b['outcomes']['exit'])
    per_map=delta.reshape(-1,n).mean(0);rng=np.random.default_rng(790013)
    boot=per_map[rng.integers(0,n,(20000,n))].mean(1)
    return dict(delta_pp=100*delta.mean(),map_cluster_95_interval_pp=(100*np.quantile(boot,[.025,.975])).tolist())


def main():
    global STOP
    torch.set_num_threads(1);SUITE.mkdir(parents=True,exist_ok=True)
    lock=(SUITE/'.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    store=Store(SUITE,4*1024**3,10*1024**3)
    def stop(*args):
        global STOP
        STOP=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    manifest=dict(source=str(SOURCE),source_sha256=digest(SOURCE),endpoints=ENDPOINTS,seed=0,
        sources={str(p):digest(p) for p in [pathlib.Path(__file__),*SCRIPTS.glob('*.py'),ROOT/'diagnostics/d1-stairs-deaths/probe.cu',ROOT/'branches/d1-stairs-v2/src/learn.cu']},
        libraries={str(p):digest(p) for p in (ROOT/'learning-runs/d1-stairs-assets').glob('stairs-clump[01].so')},
        preparation='96 training-map deaths, minus8/minus32 states;16 RNGs/action screen;independent64 RNG confirmation >=.5 exit and >=.2 gain',
        treatment='25% death-state reset worlds plus .5 supervised correction loss; unchanged exit reward, navigation KL, and .5 source replay KL in both arms',
        evaluation='validation selects endpoint by mean sampled/greedy exit, frozen baseline included; fresh test seed790011 and original regression seed950991 after selection; no test states train')
    if (SUITE/'manifest.json').exists():assert json.loads((SUITE/'manifest.json').read_text())==manifest,'Source/config drift'
    else:store.json('manifest.json',manifest)
    try:
        start=time.monotonic();model=load_model();probe=reseeder()
        bank=torch.load(SUITE/'bank.pt',weights_only=False) if (SUITE/'bank.pt').exists() else collect(model,store)
        correction=torch.load(SUITE/'corrections.pt',weights_only=False) if (SUITE/'corrections.pt').exists() else corrections(model,bank,store,probe)
        if not (SUITE/'baseline.json').exists():
            baseline={mode:evaluate(model,mode=mode) for mode in ['sampled','greedy']};store.json('baseline.json',baseline)
        else:baseline=json.loads((SUITE/'baseline.json').read_text())
        del model
        curves={}
        for arm in ['targeted','control']:
            curves[arm]=train(arm,bank,correction,store,probe)
            if STOP:status(store,phase='stopped',arm=arm);return
        selections={}
        for arm,curve in curves.items():
            all_rows=[dict(decisions=0,**baseline),*curve]
            best=max(all_rows,key=lambda r:r['sampled']['exit_rate']+r['greedy']['exit_rate'])
            selections[arm]=best['decisions']
        store.json('selection.json',dict(criterion=manifest['evaluation'],selected=selections))
        model=load_model();confirmation={}
        for cohort,seed,batch in [('fresh',790011,6400),('regression',950991,3200)]:
            confirmation[cohort]={}
            for name in ['baseline','targeted','control']:
                step=selections.get(name,0);p=SUITE/name/f'checkpoints/{step}.pt' if step else SOURCE
                model.load_state_dict(torch.load(p,map_location='cpu',weights_only=False)['model'])
                confirmation[cohort][name]={}
                for mode in ['sampled','greedy']:
                    r=evaluate(model,'test',batch,seed,mode);confirmation[cohort][name][mode]=r
                    status(store,phase='confirmation',cohort=cohort,model=name,decisions=step,mode=mode,**brief(r))
                store.json(f'confirmation-{cohort}.json',confirmation[cohort])
        comparisons={c:{name:{mode:paired(rows[name][mode],rows['baseline'][mode]) for mode in ['sampled','greedy']}
                           for name in ['targeted','control']} for c,rows in confirmation.items()}
        result=dict(manifest=manifest,baseline=baseline,curves=curves,selections=selections,confirmation=confirmation,comparisons=comparisons,
                    preparation_seconds=bank['seconds']+correction['seconds'],wall_seconds=time.monotonic()-start,
                    caveat='One training seed. Test layouts previously audited, fresh placements/RNG only; intervention design informed by prior test diagnostics. Targeted arm combines resets and action supervision.')
        store.json('result.json',result)
        (ROOT/'results/d1-stairs-survival.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        status(store,phase='complete',selections=selections,comparisons=comparisons)
    except Exception as exc:
        status(store,phase='failed',error=repr(exc));raise


if __name__=='__main__':main()
