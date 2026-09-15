#!/usr/bin/env python3
"""PPO learning curve for the fixed-map floor-clear proxy; no demos or teacher labels."""
import argparse
import hashlib
import json
import math
import pathlib
import platform
import shutil
import time
import numpy as np
import torch
from torch import nn
from torch.distributions import Categorical, Distribution
from learn_env import Env, ROOT

Distribution.set_default_validate_args(False)

ENV_SCOPE = 'one fixed native map; fresh randomized placements and combat; proxy player melee'
EXTRA_SOURCES = []
META_EXTRA = {}
TRAIN_ENV_KWARGS = {}
EVAL_ENV_KWARGS = {}

class Policy(nn.Module):
    def __init__(self, obs=206):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(obs,128),nn.Tanh(),nn.Linear(128,128),nn.Tanh())
        self.actor = nn.Linear(128,9)
        self.critic = nn.Linear(128,1)
        for layer in self.modules():
            if isinstance(layer,nn.Linear):
                nn.init.orthogonal_(layer.weight,math.sqrt(2)); nn.init.zeros_(layer.bias)
        nn.init.orthogonal_(self.actor.weight,0.01)
        nn.init.orthogonal_(self.critic.weight,1)

    def forward(self, obs, mask):
        h=self.body(obs)
        return Categorical(logits=self.actor(h).masked_fill(mask==0,-1e9)), self.critic(h).squeeze(-1)

@torch.no_grad()
def evaluate(env, policy=None, mode='greedy', seed=900000):
    env.reset(seed)
    active=torch.ones(env.batch,dtype=torch.bool,device=env.device)
    terminal=torch.zeros((env.batch,8),device=env.device)
    returns=torch.zeros(env.batch,device=env.device)
    # Preserve training RNG, and use identical eval sampling seeds across checkpoints.
    with torch.random.fork_rng(devices=[env.device.index]):
        torch.manual_seed(seed)
        for _ in range(env.limit):
            if mode=='wait':
                actions=torch.full((env.batch,),8,device=env.device,dtype=torch.int64)
            elif mode=='random':
                actions=torch.multinomial(env.mask,1).squeeze(1)
            elif mode=='pursuit':
                actions=env.heuristic()
            else:
                dist,_=policy(env.obs,env.mask)
                actions=dist.probs.argmax(-1) if mode=='greedy' else dist.sample()
            _,out=env.step(actions, active=active)
            returns+=out[:,0]*active
            ended=active & (out[:,1]>0)
            terminal[ended]=out[ended]
            active &= ~ended
    assert not active.any().item()
    t=terminal.cpu().numpy(); successes=float(t[:,2].sum()); n=env.batch
    phat=successes/n; z=1.96
    center=(phat+z*z/(2*n))/(1+z*z/n)
    half=z*math.sqrt(phat*(1-phat)/n+z*z/(4*n*n))/(1+z*z/n)
    return dict(mode=mode,eval_seed=seed,episodes=n,clear_rate=float(phat),
                clear_ci95=[center-half,center+half],enemies_killed=float(t[:,3].mean()),
                killed_fraction=float(t[:,3].mean()/env.enemies),
                mean_hp=float(t[:,4].mean()),mean_length=float(t[:,5].mean()),
                clear_length=float(t[t[:,2]>0,5].mean()) if successes else None,
                death_rate=float(t[:,6].mean()),timeout_rate=float(t[:,7].mean()),
                mean_return=float(returns.mean().item()))

def emit(path, row):
    with path.open('a') as f: f.write(json.dumps(row,allow_nan=False)+'\n')
    print(json.dumps(row,allow_nan=False),flush=True)


def train(args,seed,eval_env):
    torch.manual_seed(seed)
    env=Env(args.batch,args.enemies,seed=seed*100000+17,**TRAIN_ENV_KWARGS)
    model=Policy(env.obs.shape[1]).cuda()
    opt=torch.optim.Adam(model.parameters(),lr=args.lr,eps=1e-5)
    folder=args.output/f'seed-{seed}'; folder.mkdir(parents=True,exist_ok=False)
    log=folder/'curve.jsonl'
    total=0; train_seconds=0.; collect_seconds=0.; update_seconds=0.; update=0
    if args.resume_from:
        source=args.resume_from/f'seed-{seed}'
        rows=[json.loads(line) for line in (source/'curve.jsonl').read_text().splitlines()]
        previous=rows[-1]
        saved=torch.load(source/f"policy-{previous['decisions']}.pt",map_location='cpu',weights_only=False)
        for key in ('batch','horizon','enemies','lr','gamma','gae_lambda','entropy','epochs','minibatch'):
            if saved['config'][key]!=getattr(args,key):
                raise ValueError(f'Resume changes training setting: {key}')
        if saved['seed']!=seed or saved['decisions']!=previous['decisions']:
            raise ValueError('Checkpoint/curve identity mismatch')
        model.load_state_dict(saved['model']); opt.load_state_dict(saved['optimizer'])
        total=previous['decisions']; update=previous['updates']
        train_seconds=previous['train_seconds']; collect_seconds=previous['collection_seconds']
        update_seconds=previous['update_seconds']
        if args.steps<=total: raise ValueError('Target must exceed source checkpoint decisions')
        if 'env_state' in saved:
            env.state.copy_(saved['env_state']); env.obs.copy_(saved['env_obs']); env.mask.copy_(saved['env_mask'])
            reset_seed=None
        else:
            # Legacy checkpoints omitted live worlds; continue from fresh episodes.
            reset_seed=4000000+seed*100000
            env.reset(reset_seed)
        torch.set_rng_state(saved['torch_rng']); torch.cuda.set_rng_state(saved['cuda_rng'])
        shutil.copy2(source/'curve.jsonl',log)
        (folder/'resume.json').write_text(json.dumps(dict(source=str(source),decisions=total,
            restored=['model','optimizer','torch_rng','cuda_rng'],
            environment_restored=reset_seed is None,environment_reset_seed=reset_seed),indent=2)+'\n')
    checks=[x for x in (100000,300000,1000000,3000000,5000000,10000000,30000000) if total<x<args.steps]+[args.steps]
    def checkpoint(steps,train_seconds,collect_seconds,update_seconds,update):
        torch.cuda.synchronize(); start=time.perf_counter()
        row=dict(seed=seed,decisions=steps,updates=update,train_seconds=train_seconds,
                 collection_seconds=collect_seconds,update_seconds=update_seconds,
                 decisions_per_second=steps/train_seconds if train_seconds else None,
                 greedy=evaluate(eval_env,model,'greedy'),sampled=evaluate(eval_env,model,'sampled'))
        torch.cuda.synchronize(); row['evaluation_seconds']=time.perf_counter()-start
        emit(log,row)
        torch.save(dict(model=model.state_dict(),optimizer=opt.state_dict(),decisions=steps,
                        seed=seed,config=vars(args)|{'output':str(args.output),'resume_from':str(args.resume_from) if args.resume_from else None},
                        torch_rng=torch.get_rng_state(),cuda_rng=torch.cuda.get_rng_state(),
                        env_state=env.state.cpu(),env_obs=env.obs.cpu(),env_mask=env.mask.cpu()),folder/f'policy-{steps}.pt')
    if not args.resume_from: checkpoint(0,0,0,0,0)
    T,B=args.horizon,args.batch
    observations=torch.empty((T,B,env.obs.shape[1]),device='cuda')
    masks=torch.empty((T,B,9),device='cuda')
    actions=torch.empty((T,B),dtype=torch.int64,device='cuda')
    old_logp=torch.empty((T,B),device='cuda'); values=torch.empty_like(old_logp)
    rewards=torch.empty_like(old_logp); dones=torch.empty_like(old_logp)
    advantages=torch.empty_like(old_logp)
    flatobs=observations.flatten(0,1); flatmask=masks.flatten(0,1); flatactions=actions.flatten()
    while total<args.steps:
        torch.cuda.synchronize(); start=time.perf_counter()
        with torch.no_grad():
            for t in range(T):
                observations[t].copy_(env.obs); masks[t].copy_(env.mask)
                dist,v=model(env.obs,env.mask); a=dist.sample()
                actions[t]=a; old_logp[t]=dist.log_prob(a); values[t]=v
                _,out=env.step(a)
                rewards[t]=out[:,0]; dones[t]=out[:,1]
            _,nextv=model(env.obs,env.mask)
            gae=torch.zeros(B,device='cuda')
            for t in reversed(range(T)):
                live=1-dones[t]
                delta=rewards[t]+args.gamma*nextv*live-values[t]
                gae=delta+args.gamma*args.gae_lambda*live*gae
                advantages[t]=gae; nextv=values[t]
            returns=(advantages+values).flatten()
            adv=advantages.flatten(); adv=(adv-adv.mean())/(adv.std()+1e-8)
        torch.cuda.synchronize(); collected=time.perf_counter()-start
        learning_start=time.perf_counter()
        losses=[]
        for _ in range(args.epochs):
            indices=torch.randperm(T*B,device='cuda')
            for inds in indices.split(args.minibatch):
                dist,v=model(flatobs[inds],flatmask[inds])
                lp=dist.log_prob(flatactions[inds]); ratio=(lp-old_logp.flatten()[inds]).exp()
                pg=-torch.minimum(ratio*adv[inds],ratio.clamp(0.8,1.2)*adv[inds]).mean()
                vl=0.5*(v-returns[inds]).square().mean()
                entropy=dist.entropy().mean()
                loss=pg+0.5*vl-args.entropy*entropy
                opt.zero_grad(set_to_none=True); loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(),0.5); opt.step()
                losses.append(loss.detach())
        torch.cuda.synchronize(); learned=time.perf_counter()-learning_start
        assert torch.isfinite(torch.stack(losses)).all().item(), 'non-finite loss'
        collect_seconds+=collected; update_seconds+=learned; train_seconds+=collected+learned
        total+=T*B; update+=1
        if checks and total>=checks[0]:
            while checks and total>=checks[0]: checks.pop(0)
            checkpoint(total,train_seconds,collect_seconds,update_seconds,update)
        elif update%10==0:
            print(json.dumps(dict(progress=True,seed=seed,decisions=total,train_seconds=train_seconds,
                                  decisions_per_second=total/train_seconds)),flush=True)
    return model


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--output',type=pathlib.Path,required=True)
    ap.add_argument('--resume-from',type=pathlib.Path)
    ap.add_argument('--mode',choices=['train','baselines'],default='train')
    ap.add_argument('--enemies',type=int,default=6)
    ap.add_argument('--seeds',default='0,1,2')
    ap.add_argument('--steps',type=int,default=3000000)
    ap.add_argument('--batch',type=int,default=512)
    ap.add_argument('--horizon',type=int,default=64)
    ap.add_argument('--eval-episodes',type=int,default=1024)
    ap.add_argument('--lr',type=float,default=3e-4)
    ap.add_argument('--gamma',type=float,default=0.99)
    ap.add_argument('--gae-lambda',type=float,default=0.95)
    ap.add_argument('--entropy',type=float,default=0.01)
    ap.add_argument('--epochs',type=int,default=4)
    ap.add_argument('--minibatch',type=int,default=4096)
    args=ap.parse_args()
    torch.set_num_threads(1); torch.backends.cuda.matmul.allow_tf32=False
    if args.resume_from:
        previous=json.loads((args.resume_from/'config.json').read_text())
        for p,h in previous['sources'].items():
            if p!='scripts/train_clear.py' and hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h:
                raise ValueError(f'Resume changes simulation source: {p}')
    args.output.mkdir(parents=True,exist_ok=False)
    meta=vars(args)|META_EXTRA|{'output':str(args.output),'resume_from':str(args.resume_from) if args.resume_from else None,'torch':torch.__version__,
                    'gpu':torch.cuda.get_device_name(),'platform':platform.platform(),
                    'scope':ENV_SCOPE,
                    'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in [ROOT/'src/learn.cu',ROOT/'src/sim.h',ROOT/'scripts/learn_env.py',
                                         pathlib.Path(__file__),ROOT/'fixtures/fixture.bin'] + EXTRA_SOURCES}}
    (args.output/'config.json').write_text(json.dumps(meta,indent=2)+'\n')
    env=Env(args.eval_episodes,args.enemies,seed=900000,**EVAL_ENV_KWARGS)
    for mode in ('wait','random','pursuit'):
        emit(args.output/'baselines.jsonl',evaluate(env,mode=mode))
    if args.mode=='train':
        for seed in map(int,args.seeds.split(',')): train(args,seed,env)

if __name__=='__main__': main()
