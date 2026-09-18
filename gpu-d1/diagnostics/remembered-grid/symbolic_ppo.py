"""On-policy recurrent PPO on the existing symbolic navigation fixtures.

Synchronous complete episodes; terminal suffixes masked. Sequence starts use
stored rollout hidden states (detached), with BPTT through 16 learning steps.
No teacher labels, imitation loss, augmentation, or replay of old episodes.
"""
import argparse, fcntl, hashlib, json, time
from pathlib import Path
import torch
from run import evaluate, save_json
from runtime import Env, OUT, ROOT, build
from optimize_symbolic import load
from symbolic_execution import PolicyExecution, StaticInference


def gae_returns(reward, value, done, active, gamma=.999, lam=.95):
    advantage=torch.zeros_like(value); carry=torch.zeros_like(value[0]); following=carry.clone()
    for t in reversed(range(len(value))):
        delta=reward[t]+gamma*following*(~done[t])-value[t]
        carry=(delta+gamma*lam*(~done[t])*carry)*active[t]
        advantage[t]=carry;following=value[t]*active[t]
    return advantage, advantage+value


def sequences(x):
    # [time,env,...] -> [env * chunks,16,...]; never cross an episode.
    return x.transpose(0,1).reshape(-1,16,*x.shape[2:])


@torch.no_grad()
def collect(env, model, policy, seed, gae_lambda=.95):
    env.reset(seed=seed,labels=False);policy.reset_cache();rows=[];prepared=[];starts=[]
    for t in range(256):
        if t%16==0:
            starts.append(torch.zeros(env.batch,128,device='cuda') if policy.hidden is None else policy.hidden.clone())
        p=model.prepare(env.grid,env.stats);prepared.append(tuple(z.clone() for z in p))
        mask=env.mask.clone();active=env.active.clone()
        logits,value=policy.outputs(env.grid,mask,env.stats)
        # Graph outputs alias storage: save values before the next replay.
        value=value.clone();dist=torch.distributions.Categorical(logits=logits,validate_args=False)
        action=dist.sample();logp=dist.log_prob(action)
        env.step(action,limit=256,labels=False)
        done=active & ~env.active;reward=(env.out[:,2]-env.out[:,6])*done
        rows.append((mask,action,logp,value,reward,done,active))
    assert not env.active.any(), 'Complete-episode GAE requires all episodes terminal'
    mask,action,logp,value,reward,done,active=[torch.stack(z) for z in zip(*rows)]
    adv,ret=gae_returns(reward,value,done,active,lam=gae_lambda)
    mean=adv[active].mean();std=adv[active].std().clamp_min(1e-8);adv=(adv-mean)/std
    data=[sequences(torch.stack(z)) for z in zip(*prepared)]
    data += [sequences(z) for z in (mask,action,logp,adv,ret,active)]
    hidden=torch.stack(starts).transpose(0,1).reshape(-1,128)
    keep=data[-1].any(1);data=[z[keep] for z in data];hidden=hidden[keep]
    count=int(active.sum());summary=dict(exit=float((reward==1).sum()/env.batch),death=float((reward==-1).sum()/env.batch),active_fraction=count/active.numel())
    return data,hidden,count,summary


def minibatch(model, execution, data, hidden, ix, mode="joint"):
    valid_sequences=len(ix)
    if valid_sequences<128:ix=torch.cat([ix,ix[:1].expand(128-valid_sequences)])
    p=[z[ix].flatten(0,1) for z in data[:4]]
    mask,action,oldlp,adv,ret,valid=[z[ix] for z in data[4:]]
    valid=valid.clone();valid[valid_sequences:]=False
    with torch.autocast('cuda',dtype=torch.float16):
        x=execution.encode(p).reshape(len(ix),16,-1)
        z,_=model.sequence(x,hidden[ix])
        logits,value=execution.heads(z,mask)
        if mode=="detached_critic":value=model.value(z.detach()).float().squeeze(-1)
    d=torch.distributions.Categorical(logits=logits,validate_args=False)
    logratio=d.log_prob(action)-oldlp;ratio=logratio.exp()
    n=valid.sum().clamp_min(1)
    avg=lambda x:(x*valid).sum()/n
    actor=avg(-torch.minimum(ratio*adv,ratio.clamp(.8,1.2)*adv))-.001*avg(d.entropy())
    critic=.25*avg((value-ret).square())
    loss=(0 if mode=="critic_only" else 1)*actor+(0 if mode=="actor_only" else 1)*critic
    return loss,avg((ratio-1)-logratio),logratio[valid]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--decisions',type=int,default=1000000);ap.add_argument('--name',default='symbolic-ppo-seed0');ap.add_argument('--smoke',action='store_true');ap.add_argument('--mode',choices=['joint','detached_critic','critic_only','actor_only'],default='joint');ap.add_argument('--gae-lambda',type=float,default=.95);args=ap.parse_args()
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True;build()
    folder=OUT/args.name;folder.mkdir(exist_ok=True);lock=(folder/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (folder/'latest.pt').exists():raise RuntimeError('Refusing to overwrite checkpoint')
    model=load(True).configure_encoder(True,True);execution=PolicyExecution(model,compiled=True)
    policy=StaticInference(execution,amp=True,graphed=True)
    opt=torch.optim.Adam(model.parameters(),lr=1e-5);scaler=torch.amp.GradScaler('cuda')
    manifest=dict(mode=args.mode,seed=0,target=args.decisions,map_size=[32,32],envs=128,deadline=256,sequence_length=16,sequence_batch=128,epochs=4,lr=1e-5,gamma=.999,gae_lambda=args.gae_lambda,entropy=.001,value_coefficient=.25,clip=.2,rewards=dict(exit=1,death=-1,timeout=0),source_sha256=hashlib.sha256((OUT/'symbolic-gru/best.pt').read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scope='Actual recurrent PPO, all layers trainable; stored initial hidden state, no burn-in. Compiled encoders/heads, cuDNN sequence, graphed inference, eager optimizer/backward. Synthetic navigation, not ordinary Crawl floors.')
    save_json(folder/'manifest.json',manifest)
    def assess():
        result={}
        # Evaluation must not alter training RNG or optimizer state.
        with torch.random.fork_rng(devices=[0]):
            for split,mode in [('validation','greedy'),('test','greedy'),('long','greedy'),('test','sampled')]:
                torch.manual_seed(11812);result[split+'_'+mode]=evaluate(policy,split,mode=mode)['summary']
        return result
    report=dict(manifest=manifest,baseline={} if args.smoke else assess(),history=[],checkpoints=[])
    save_json(folder/'progress.json',report);env=Env('train',128);decisions=0;wave=0;training=0.;milestones=[100000,500000,args.decisions]
    while decisions<args.decisions:
        start=time.monotonic();data,h,n,summary=collect(env,model,policy,1000+wave,args.gae_lambda)
        torch.cuda.synchronize();collection=time.monotonic()-start;optimization_start=time.monotonic()
        # Before updates, sequence replay must reproduce behavior log-probabilities.
        with torch.no_grad():
            _,_,delta=minibatch(model,execution,data,h,torch.arange(min(128,len(h)),device='cuda'))
            mismatch=float(delta.abs().max()) if len(delta) else 0.
            assert mismatch<.03, f'Rollout/replay mismatch {mismatch}'
        losses=[];kls=[];stop=False;overflow_skips=0
        for epoch in range(4):
            for ix in torch.randperm(len(h),device='cuda').split(128):
                if not data[-1][ix].any():continue
                opt.zero_grad(set_to_none=True);loss,kl,_=minibatch(model,execution,data,h,ix,args.mode)
                # Conservative early stop before applying a large policy update.
                if float(kl)>.02:stop=True;break
                assert torch.isfinite(loss), "Nonfinite PPO loss"
                scaler.scale(loss).backward();scaler.unscale_(opt)
                assert all(p.grad is not None for p in model.parameters())
                if not torch.stack([torch.isfinite(p.grad).all() for p in model.parameters()]).all():
                    # Expected AMP overflow: GradScaler skips Adam and lowers scale.
                    scaler.step(opt);scaler.update();overflow_skips+=1;continue
                torch.nn.utils.clip_grad_norm_(model.parameters(),.5);scaler.step(opt);scaler.update()
                losses.append(float(loss.detach()));kls.append(float(kl.detach()))
            if stop:break
        torch.cuda.synchronize();optimization=time.monotonic()-optimization_start;training+=time.monotonic()-start;decisions+=n;wave+=1
        row=dict(wave=wave,decisions=decisions,training_seconds=training,decisions_per_second=decisions/training,collection_seconds=collection,optimization_seconds=optimization,rollout_replay_max_logprob_difference=mismatch,loss=sum(losses)/max(1,len(losses)),approx_kl=sum(kls)/max(1,len(kls)),updates=len(losses),overflow_skips=overflow_skips,kl_early_stop=stop,**summary)
        report['history'].append(row);print(json.dumps(row),flush=True)
        del data,h
        crossed=[v for v in milestones if v<=decisions]
        if crossed or args.smoke:
            metrics={} if args.smoke else assess();entry=dict(decisions=decisions,milestones=crossed,metrics=metrics);report['checkpoints'].append(entry)
            payload=dict(model=model.state_dict(),optimizer=opt.state_dict(),scaler=scaler.state_dict(),decisions=decisions)
            torch.save(payload,folder/'latest.pt')
            if crossed:torch.save(payload,folder/('checkpoint-'+str(max(crossed))+'.pt'))
            milestones=[v for v in milestones if v>decisions];print('EVALUATION '+json.dumps(entry),flush=True)
        save_json(folder/'progress.json',report)
        if args.smoke:break
    report['finished']=True;save_json(folder/'progress.json',report);save_json(ROOT/'results'/(args.name+'.json'),report)

if __name__=='__main__':main()
