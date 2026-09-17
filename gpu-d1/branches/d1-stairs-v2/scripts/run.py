"""Bounded D1 stairs adaptation, frozen comparison, and short PPO continuation."""
import copy
import fcntl
import hashlib
import json
import math
import pathlib
import signal
import time
import numpy as np
import torch
from ablation_storage import Store
from common import ROOT,SUITE,SOURCE,REFERENCE,BUFFER,env,expand_weights,pad,weights,NavigationAnchor
from evaluate import evaluate
from tactical_models import Policy

MIB=1024**2
ENDPOINTS=[500224,1000448,3000320]

def digest(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def brief(r):
    return {k:r[k] for k in ['exit_rate','death_rate','timeout_rate','turns','discovery_rate','enemies_alive_on_exit']}

def bootstrap(model,store):
    """Only teach post-discovery MOVE and DESCEND; preserve prior behavior by KL."""
    before=copy.deepcopy(model).eval().requires_grad_(False)
    e=env('train',256,971)
    xs=[];ms=[];ys=[];seen=0;decisions=0;teacher_exits=0
    torch.cuda.synchronize();started=time.monotonic()
    with torch.no_grad():
        for _ in range(512):
            teacher=e.heuristic().clone()
            known=e.obs[:,999]>0;awake=(e.obs[:,959:999]<0).any(-1)
            eligible=known&((~awake&(teacher<8))|(teacher==18))
            if eligible.any() and seen<65536:
                x=e.obs[eligible].clone();m=e.mask[eligible].clone();y=teacher[eligible].clone()
                count=min(len(x),65536-seen);xs.append(x[:count]);ms.append(m[:count]);ys.append(y[:count]);seen+=count
            action=torch.where(known,teacher,before(e.obs,e.mask)[0].sample())
            assert (e.mask.gather(1,action[:,None])>0).all()
            e.step(action);teacher_exits+=int(e.out[:,2].sum());decisions+=e.batch
    x,m,y=torch.cat(xs),torch.cat(ms),torch.cat(ys)
    assert ((y<8)|(y==18)).all()
    stairs=torch.where(y==18)[0];move=torch.where(y<8)[0]
    assert len(stairs)>=64 and len(move)>=1024,(len(stairs),len(move))
    torch.cuda.synchronize();collection_seconds=time.monotonic()-started
    replay=torch.load(BUFFER,map_location='cuda',weights_only=False);rx,rm=pad(replay['obs'],replay['mask'])
    opt=torch.optim.Adam(model.parameters(),lr=.0003,eps=1e-5)
    losses=[];started=time.monotonic()
    for update in range(500):
        # Prevent the rare explicit DESCEND examples from being swamped by moves.
        ids=torch.cat((stairs[torch.randint(len(stairs),(128,),device='cuda')],move[torch.randint(len(move),(384,),device='cuda')]))
        a=model(x[ids],m[ids])[0];ce=-a.log_prob(y[ids]).mean()
        ix=torch.randint(len(rx),(512,),device='cuda')
        with torch.no_grad():target=before(rx[ix],rm[ix])[0].probs
        actual=model(rx[ix],rm[ix])[0].probs
        kl=(target*(target.clamp_min(1e-30).log()-actual.clamp_min(1e-30).log())).sum(-1).mean()
        loss=ce+kl;assert torch.isfinite(loss)
        opt.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),.5);opt.step()
        if update%100==0:losses.append(dict(update=update,cross_entropy=float(ce),source_kl=float(kl)))
    torch.cuda.synchronize();training_seconds=time.monotonic()-started
    report=dict(collection_decisions=decisions,collection_seconds=collection_seconds,training_seconds=training_seconds,
        teacher_rollout_exits=teacher_exits,examples=len(y),descend_examples=len(stairs),move_examples=len(move),
        minibatches=500,examples_per_minibatch=512,losses=losses,
        note='Source actions before discovery; scripted actions afterwards during collection. Only post-discovery navigation/descend labels are fitted. Replay KL protects prior policy. All demonstrations use training maps.')
    store.atomic('adapted.pt',lambda f:torch.save(dict(model=weights(model),bootstrap=report),f),16*MIB)
    store.json('bootstrap.json',report)
    print('Interface adaptation',report,flush=True)
    return report

def paired(a,b,seed=950992):
    n=len(a['maps']);delta=np.array(a['outcomes']['exit'])-np.array(b['outcomes']['exit'])
    per_map=delta.reshape(-1,n).mean(0);rng=np.random.default_rng(seed)
    boot=per_map[rng.integers(0,n,(20000,n))].mean(1)
    return dict(delta_percentage_points=100*delta.mean(),map_cluster_95_percent_interval=(100*np.quantile(boot,[.025,.975])).tolist())

def main():
    torch.set_num_threads(1);SUITE.mkdir(parents=True,exist_ok=True)
    lock=(SUITE/'.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    store=Store(SUITE,4*1024**3,10*1024**3);wall_start=time.monotonic()
    sources=[*pathlib.Path(__file__).parent.glob('*.py'),*pathlib.Path(__file__).parents[1].joinpath('src').glob('*')]
    manifest=dict(source=str(SOURCE),source_sha256=digest(SOURCE),reference_sha256=digest(REFERENCE),buffer_sha256=digest(BUFFER),
        source_decisions=36000768,training_seed=0,endpoints=ENDPOINTS,
        files={str(p):digest(p) for p in sources},libraries={str(p):digest(p) for p in (ROOT/'learning-runs/d1-stairs-assets').glob('stairs-clump[01].so')},
        config=dict(enemies=24,turns=2048,stairs=3,exit_reward=1,turn_penalty=.00001,gamma=1,gae_lambda=.95,lr=.0003,entropy=0,
                    batch=512,horizon=64,minibatch=4096,epochs=4,anchor_weight=1,anchor_scope='no_known_stair_and_no_visible_awake',
                    wait_correction=False,optimizer='Fresh Adam after interface adaptation; expanded task resets simulator and optimizer state'))
    if (SUITE/'manifest.json').exists():assert json.loads((SUITE/'manifest.json').read_text())==manifest,'Source/configuration drift'
    else:store.json('manifest.json',manifest)
    torch.manual_seed(0)
    saved=torch.load(SOURCE,map_location='cpu',weights_only=False);assert saved['decisions']==36000768
    model=expand_weights(saved['model']);del saved
    try:
        if not (SUITE/'raw-interface.json').exists():
            store.json('status.json',dict(status='evaluating_original_interface'))
            r=evaluate(model,batch=1024);store.json('raw-interface.json',r);print('Before interface adaptation',brief(r),flush=True)
        if (SUITE/'adapted.pt').exists():model.load_state_dict(torch.load(SUITE/'adapted.pt',map_location='cpu',weights_only=False)['model'])
        else:
            store.json('status.json',dict(status='interface_adaptation'));bootstrap(model,store)
        if not (SUITE/'baseline.json').exists():
            store.json('status.json',dict(status='evaluating_frozen_adapted_baseline'))
            baseline={}
            for mode in ['sampled','greedy','teacher']:
                baseline[mode]=evaluate(model,mode=mode);print('Frozen baseline',mode,brief(baseline[mode]),flush=True)
            store.json('baseline.json',baseline)
        anchor=NavigationAnchor();e=env('train',512,0)
        opt=torch.optim.Adam(model.parameters(),lr=.0003,eps=1e-5)
        total=0;training_seconds=0.;training_turns=0;history=[]
        if (SUITE/'latest.pt').exists():
            c=torch.load(SUITE/'latest.pt',map_location='cpu',weights_only=False)
            model.load_state_dict(c['model']);opt.load_state_dict(c['optimizer'])
            e.state.copy_(c['env_state']);e.obs.copy_(c['env_obs']);e.mask.copy_(c['env_mask'])
            total=c['decisions'];training_seconds=c['training_seconds'];training_turns=c['training_turns'];history=c['history']
            torch.set_rng_state(c['torch_rng']);torch.cuda.set_rng_state(c['cuda_rng']);del c
        else:torch.manual_seed(0)
        stop=[False]
        def interrupt(*args):stop[0]=True
        signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGINT,interrupt)
        def persist():
            c=dict(model=weights(model),optimizer=opt.state_dict(),decisions=total,training_seconds=training_seconds,training_turns=training_turns,
                   history=history,env_state=e.state.cpu(),env_obs=e.obs.cpu(),env_mask=e.mask.cpu(),torch_rng=torch.get_rng_state(),cuda_rng=torch.cuda.get_rng_state())
            store.atomic('latest.pt',lambda f:torch.save(c,f),256*MIB)
        obs=torch.empty(64,512,1015,device='cuda');mask=torch.empty(64,512,19,device='cuda')
        actions=torch.empty(64,512,device='cuda',dtype=torch.long)
        lp,val,rew,done,adv=[torch.empty(64,512,device='cuda') for _ in range(5)]
        while total<ENDPOINTS[-1] and not stop[0]:
            endpoint=min(x for x in ENDPOINTS if x>total);T=min(64,math.ceil((endpoint-total)/512))
            store.ensure(256*MIB);torch.cuda.synchronize();start=time.monotonic();turns=torch.zeros((),device='cuda')
            with torch.no_grad():
                for t in range(T):
                    obs[t]=e.obs;mask[t]=e.mask;d,v=model(e.obs,e.mask);a=d.sample()
                    actions[t]=a;lp[t]=d.log_prob(a);val[t]=v;e.step(a)
                    rew[t]=e.out[:,40];done[t]=e.out[:,1];turns+=e.out[:,26].sum()
                nextv=model(e.obs,e.mask)[1];gae=torch.zeros(512,device='cuda')
                for t in reversed(range(T)):
                    live=1-done[t];delta=rew[t]+live*nextv-val[t]
                    gae=delta+.95*live*gae;adv[t]=gae;nextv=val[t]
                returns=(val[:T]+adv[:T]).flatten();advantages=adv[:T].flatten();advantages=(advantages-advantages.mean())/(advantages.std()+1e-8)
            x=obs[:T].flatten(0,1);m=mask[:T].flatten(0,1)
            for _ in range(4):
                for ix in torch.randperm(T*512,device='cuda').split(4096):
                    d,v=model(x[ix],m[ix]);ratio=(d.log_prob(actions[:T].flatten()[ix])-lp[:T].flatten()[ix]).exp()
                    pg=-torch.minimum(ratio*advantages[ix],ratio.clamp(.8,1.2)*advantages[ix]).mean()
                    loss=pg+.25*(v-returns[ix]).square().mean()+anchor.loss(model,x[ix],m[ix])
                    assert torch.isfinite(loss),'Non-finite PPO loss'
                    opt.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),.5);opt.step()
            torch.cuda.synchronize();training_seconds+=time.monotonic()-start;training_turns+=int(turns);total+=T*512
            if total==endpoint:
                row=dict(decisions=total,training_seconds=training_seconds,training_turns=training_turns)
                store.json('status.json',dict(status='evaluating',decisions=total,training_seconds=training_seconds))
                for mode in ['sampled','greedy']:
                    row[mode]=evaluate(model,mode=mode);print('PPO',total,mode,brief(row[mode]),flush=True)
                history.append(row);store.json('curve.json',history)
                store.atomic(f'checkpoints/{total}.pt',lambda f:torch.save(dict(model=weights(model),decisions=total),f),16*MIB)
                persist()
            elif total%327680==0:
                store.json('status.json',dict(status='training',decisions=total,training_seconds=training_seconds,estimated_remaining_training_seconds=training_seconds/total*(ENDPOINTS[-1]-total)))
            if stop[0]:persist()
        if stop[0]:store.json('status.json',dict(status='stopped',decisions=total));return
        # Freeze selection on validation before reading test outcomes.
        selected=max(history,key=lambda r:r['sampled']['exit_rate']+r['greedy']['exit_rate'])['decisions']
        store.json('selection.json',dict(decisions=selected,criterion='Mean sampled/greedy validation exit rate over the three predeclared PPO endpoints',seed=950991))
        confirmation={}
        for name,path in [('adapted',SUITE/'adapted.pt'),('ppo',SUITE/f'checkpoints/{selected}.pt')]:
            model.load_state_dict(torch.load(path,map_location='cpu',weights_only=False)['model']);confirmation[name]={}
            store.json('status.json',dict(status='test_confirmation',model=name,selected_decisions=selected))
            for mode in ['sampled','greedy']:
                confirmation[name][mode]=evaluate(model,'test',3200,950991,mode)
                print('Test',name,mode,brief(confirmation[name][mode]),flush=True)
        comparisons={m:paired(confirmation['ppo'][m],confirmation['adapted'][m]) for m in ['sampled','greedy']}
        result=dict(manifest=manifest,raw_interface=json.loads((SUITE/'raw-interface.json').read_text()),
                    bootstrap=json.loads((SUITE/'bootstrap.json').read_text()),baseline=json.loads((SUITE/'baseline.json').read_text()),
                    curve=history,selected_decisions=selected,confirmation=confirmation,comparisons=comparisons,
                    training_seconds=training_seconds,wall_seconds=time.monotonic()-wall_start,
                    caveat='One training seed. Test layouts were used in prior tasks, but not to fit or select this stairs policy. Map-cluster intervals exclude training-seed uncertainty.')
        store.json('result.json',result)
        (ROOT/'results/d1-stairs-v2.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        store.json('status.json',dict(status='complete',selected_decisions=selected,training_seconds=training_seconds,wall_seconds=result['wall_seconds']))
        print('Complete',comparisons,flush=True)
    except Exception as exc:
        store.json('status.json',dict(status='failed',error=str(exc)));raise

if __name__=='__main__':main()
