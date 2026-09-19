"""PPO continuation, no imitation loss; stored observations/masks/selected goals.

Critic consumes detached actor features. Terminals reset independently. Rollout
cutoffs bootstrap; actual deaths, timeouts and exits do not bootstrap. Gamma=1
and physical-turn cost correctly charge macro REST duration.
"""
import argparse,ctypes as C,hashlib,json,time,fcntl
from pathlib import Path
import torch
from torch import nn
from route_threat import ThreatPolicy,Agent,ThreatEnv,build,evaluate,S,ROOT,HERE,FOLDER_OUT,save_json

class PPO(nn.Module):
    def __init__(self,source):
        super().__init__();self.actor=ThreatPolicy().cuda();self.actor.load_state_dict(torch.load(source,weights_only=False)['model'])
        self.value=nn.Sequential(nn.Linear(16,64),nn.Tanh(),nn.Linear(64,1)).cuda()
        nn.init.zeros_(self.value[-1].weight);nn.init.zeros_(self.value[-1].bias)
    def forward(self,x,mask):
        with torch.autocast('cuda',dtype=torch.float16):
            logits,features=self.actor(x,return_features=True);value=self.value(features.detach()).squeeze(-1)
        return torch.distributions.Categorical(logits=logits.float().masked_fill(~mask,-1e9),validate_args=False),value.float()

def gae(reward,value,done,bootstrap,lam=.95):
    adv=torch.zeros_like(value);carry=torch.zeros_like(bootstrap);following=bootstrap
    for t in range(len(value)-1,-1,-1):
        carry=reward[t]+following*(~done[t])-value[t]+lam*carry*(~done[t]);adv[t]=carry;following=value[t]
    return adv,adv+value

def reset_done(e,agent,done):
    e.lib.threat_reset_done.argtypes=[C.c_void_p,C.c_void_p,C.c_int]+[C.c_void_p]*4
    e.check(e.lib.threat_reset_done(e.state.data_ptr(),e.memory.data_ptr(),e.batch,C.byref(e.config),C.byref(e.tables),e.active.data_ptr(),e.stream))
    agent.goal=torch.where(done,-1,agent.goal);e.observe()

@torch.no_grad()
def collect(e,agent,model,steps=64):
    rows=[];counts=torch.zeros(5,device='cuda');elapsed=torch.zeros((),device='cuda')
    for _ in range(steps):
        x,mask,_,first=agent.prepare(e,labels=False)
        # Store exactly the precision replay will use, including fractional time.
        x=x.half();dist,value=model(x,mask);choice=dist.sample();logp=dist.log_prob(choice)
        agent.goal=torch.where(choice<S,choice,agent.goal)
        step=first.gather(1,agent.goal.clamp_min(0)[:,None]).squeeze(1).long();action=torch.where(choice<=S,step,choice-(S+1))
        assert (action>=0).all() and e.mask.gather(1,action[:,None]).all()
        before=e.meta[:,5].clone();e.step(action);done=~e.active;turns=(e.meta[:,5]-before).float();assert (turns>=1).all()
        reward=done.float()*e.out[:,2]-1e-5*turns
        counts[:3]+=torch.stack([(done*e.out[:,j]).sum() for j in [2,6,7]])
        counts[3]+=(action==17).sum();counts[4]+=turns.sum();elapsed+=done.sum()
        rows.append((x,mask,choice,logp,value,reward,done))
        reset_done(e,agent,done)
    x,mask,_,_=agent.prepare(e,labels=False);_,bootstrap=model(x.half(),mask)
    x,mask,action,lp,v,r,done=[torch.stack(z) for z in zip(*rows)]
    adv,ret=gae(r,v,done,bootstrap)
    adv=(adv-adv.mean())/adv.std(unbiased=False).clamp_min(1e-8)
    data=[z.flatten(0,1) for z in (x,mask,action,lp,adv,ret)]
    metrics=dict(episodes=int(elapsed),exits=int(counts[0]),deaths=int(counts[1]),timeouts=int(counts[2]),rests=int(counts[3]),physical_turns=int(counts[4]))
    return data,metrics

class SampledAgent(Agent):
    def decide(self,e,expert=False,erase_memory=False):
        return super().decide(e,expert,erase_memory,sample=True)

@torch.no_grad()
def assess(model,memory,small=False):
    result={}
    with torch.random.fork_rng(devices=[0]):
        torch.manual_seed(80000);agent=Agent(model.actor,memory)
        result['ordinary']=evaluate(agent,split='test',small=small)
        torch.manual_seed(80000)
        result['ordinary_sampled']=evaluate(SampledAgent(model.actor,memory),split='test',small=small)
        if not small:result['pressure']=evaluate(agent,pressure=True)
    return result

def update(model,opt,scaler,data,epochs=4):
    x,mask,action,oldlp,adv,ret=data;n=len(x)
    with torch.no_grad():
        mismatch=max(float((model(x[ix],mask[ix])[0].log_prob(action[ix])-oldlp[ix]).abs().max()) for ix in torch.arange(n,device='cuda').split(64))
    assert mismatch<.01, f'Rollout/replay mismatch {mismatch}'
    stats=[];stopped=False;skipped=0
    for epoch in range(epochs):
        for ix in torch.randperm(n,device='cuda').split(64):
            dist,value=model(x[ix],mask[ix]);delta=dist.log_prob(action[ix])-oldlp[ix];ratio=delta.exp();kl=((ratio-1)-delta).mean()
            if float(kl)>.01:stopped=True;break
            actor=-torch.minimum(ratio*adv[ix],ratio.clamp(.8,1.2)*adv[ix]).mean();critic=.25*(value-ret[ix]).square().mean();loss=actor+critic
            assert torch.isfinite(loss);opt.zero_grad(set_to_none=True);scaler.scale(loss).backward();scaler.unscale_(opt)
            norm=nn.utils.clip_grad_norm_(model.parameters(),.5);oldscale=scaler.get_scale();scaler.step(opt);scaler.update();skipped+=scaler.get_scale()<oldscale
            stats.append((float(actor.detach()),float(critic.detach()),float(kl.detach()),float(norm)))
        if stopped:break
    return dict(replay_max_logprob_error=mismatch,updates=len(stats),kl_early_stop=stopped,amp_skips=skipped,mean_kl=sum(z[2] for z in stats)/max(1,len(stats)))

def checks():
    # Terminal reset boundary and truncated-rollout bootstrap have distinct targets.
    r=torch.tensor([[0.],[1.],[0.]],device='cuda');v=torch.zeros_like(r);done=torch.tensor([[False],[True],[False]],device='cuda')
    a,t=gae(r,v,done,torch.tensor([.7],device='cuda'),lam=1)
    torch.testing.assert_close(t,torch.tensor([[1.],[1.],[.7]],device='cuda'))
    # Physical-turn accounting: REST lasting ten turns costs ten times a move.
    assert abs(float((-1e-5*torch.tensor(10.)).item())+1e-4)<1e-10


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['visible','memory'],required=True);p.add_argument('--decisions',type=int,default=500000);p.add_argument('--smoke',action='store_true');p.add_argument('--tag',default='');args=p.parse_args()
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True;build();checks()
    name='route-threat-ppo-'+args.arm+('-smoke' if args.smoke else '')+args.tag;folder=FOLDER_OUT/name;folder.mkdir(exist_ok=True)
    lock=(folder/'run.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (folder/'latest.pt').exists():raise RuntimeError('Refusing to overwrite')
    source=FOLDER_OUT/f'route-threat-{args.arm}'/'selected.pt';model=PPO(source);agent=Agent(model.actor,args.arm=='memory');e=ThreatEnv('train',32);e.reset(40000)
    # Critic gradients may never alter actor parameters.
    x,m,_,_=agent.prepare(e,labels=False);_,value=model(x.half(),m);value.sum().backward();assert all(p.grad is None for p in model.actor.parameters());model.zero_grad(set_to_none=True)
    if args.smoke:
        prior=e.state[1:].clone();e.active[0]=False;done=~e.active.clone();reset_done(e,agent,done)
        assert torch.equal(prior,e.state[1:]) and e.active.all() and agent.goal[0]==-1 and e.meta[0,5]==0
    opt=torch.optim.Adam([{'params':model.actor.parameters(),'lr':1e-5},{'params':model.value.parameters(),'lr':1e-4}]);scaler=torch.amp.GradScaler('cuda',init_scale=1024)
    report=dict(arm=args.arm,seed=0,target=args.decisions,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),config=dict(envs=32,rollout=64,epochs=4,minibatch=64,actor_lr=1e-5,critic_lr=1e-4,gamma=1,gae_lambda=.95,entropy=0,clip=.2,kl_stop=.01,critic_detached=True,exit_reward=1,turn_penalty=.00001,death_reward=0,deadline=2048,imitation_loss=False),history=[],evaluations=[],source_hashes={q.name:hashlib.sha256(q.read_bytes()).hexdigest() for q in [Path(__file__),HERE/'route_threat.py',HERE/'route_threat_native.cu']})
    path=ROOT/'results'/f'{name}.json'
    if not args.smoke:report['baseline']=assess(model,args.arm=='memory');save_json(path,report);print('baseline', {k:v['groups'] for k,v in report['baseline'].items()},flush=True)
    decisions=0;training=0.;milestones=[100000,500000]
    while decisions<args.decisions:
        start=time.monotonic();data,metrics=collect(e,agent,model,64);collected=time.monotonic()-start
        diagnostic=update(model,opt,scaler,data,4);torch.cuda.synchronize();training+=time.monotonic()-start;decisions+=len(data[0]);del data
        row=dict(decisions=decisions,training_seconds=training,decisions_per_second=decisions/training,collection_seconds=collected,**metrics,**diagnostic);report['history'].append(row);print(json.dumps(row),flush=True)
        crossed=[v for v in milestones if decisions>=v]
        if crossed or decisions>=args.decisions or args.smoke:
            metrics={} if args.smoke else assess(model,args.arm=='memory');report['evaluations'].append(dict(decisions=decisions,metrics=metrics))
            payload=dict(model=model.actor.state_dict(),critic=model.value.state_dict(),optimizer=opt.state_dict(),scaler=scaler.state_dict(),decisions=decisions,cpu_rng=torch.get_rng_state(),cuda_rng=torch.cuda.get_rng_state_all())
            torch.save(payload,folder/'latest.pt')
            if crossed:torch.save(payload,folder/f'checkpoint-{max(crossed)}.pt')
            milestones=[v for v in milestones if v>decisions];print('evaluation',decisions,{k:v['groups'] for k,v in metrics.items()},flush=True)
        save_json(path,report)
        if args.smoke:break
    report['finished']=True;save_json(path,report)

if __name__=='__main__':main()
