"""Short representative PPO benchmark from a mature checkpoint; writes no checkpoints."""
import argparse,json,pathlib,time,statistics,contextlib
import torch
from torch import nn
from torch.distributions import Categorical,Distribution
from learn_env_ring_multi import Env
from learn_env import ROOT

class Policy(nn.Module):
    def __init__(self,obs,actions):
        super().__init__()
        self.body=nn.Sequential(nn.Linear(obs,128),nn.Tanh(),nn.Linear(128,128),nn.Tanh())
        self.actor=nn.Linear(128,actions);self.critic=nn.Linear(128,1)
    def forward(self,obs,mask):
        h=self.body(obs)
        return Categorical(logits=self.actor(h).masked_fill(mask==0,-1e9)),self.critic(h).squeeze(-1)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--library',type=pathlib.Path)
    ap.add_argument('--mode',choices=['baseline','async','fused'],default='baseline')
    ap.add_argument('--updates',type=int,default=12)
    ap.add_argument('--warmup',type=int,default=2)
    ap.add_argument('--output',type=pathlib.Path,required=True)
    ap.add_argument('--nsys',action='store_true')
    ap.add_argument('--torch-profile',action='store_true')
    args=ap.parse_args()
    torch.set_num_threads(1);torch.manual_seed(0)
    torch.backends.cuda.matmul.allow_tf32=False
    Distribution.set_default_validate_args(False)
    suite=ROOT.parents[1]/'learning-runs/ogre2-baseline-150m'
    lib=args.library or suite/'build/ring-reward2-frontier1-route1-ogres2-features0.so'
    saved=torch.load(suite/'runs/ogre2_base-seed0/latest.pt',map_location='cpu',weights_only=False)
    env=Env(512,26,corpus=ROOT.parents[1]/'fixtures/d1-corpus-388/train',map_limit=256,library_path=lib)
    assert env.state.shape==saved['env_state'].shape
    env.state.copy_(saved['env_state']);env.obs.copy_(saved['env_obs']);env.mask.copy_(saved['env_mask'])
    model=Policy(env.obs.shape[1],env.mask.shape[1]).cuda();model.load_state_dict(saved['model'])
    opt=torch.optim.Adam(model.parameters(),lr=.0003,eps=1e-5,fused=True if args.mode=='fused' else None)
    opt.load_state_dict(saved['optimizer'])
    if args.mode=='fused':
        for group in opt.param_groups:group['fused']=True;group['foreach']=False
        for state in opt.state.values():state['step']=state['step'].cuda()
    torch.set_rng_state(saved['torch_rng']);torch.cuda.set_rng_state(saved['cuda_rng'])
    del saved
    T,B=64,512
    observations=torch.empty((T,B,env.obs.shape[1]),device='cuda');masks=torch.empty((T,B,env.mask.shape[1]),device='cuda')
    actions=torch.empty((T,B),dtype=torch.int64,device='cuda')
    oldlp,values,rewards,dones,advantages=[torch.empty((T,B),device='cuda') for _ in range(5)]
    def update():
        timings={};torch.cuda.synchronize();start=time.perf_counter();phase=start
        with torch.no_grad(),torch.cuda.nvtx.range('rollout'):
            for t in range(T):
                observations[t].copy_(env.obs);masks[t].copy_(env.mask)
                dist,v=model(env.obs,env.mask);a=dist.sample()
                actions[t]=a;oldlp[t]=dist.log_prob(a);values[t]=v
                _,out=env.step(a);rewards[t]=out[:,0];dones[t]=out[:,1]
        torch.cuda.synchronize();now=time.perf_counter();timings['rollout_s']=now-phase;phase=now
        with torch.no_grad(),torch.cuda.nvtx.range('gae'):
            _,nextv=model(env.obs,env.mask);gae=torch.zeros(B,device='cuda')
            for t in reversed(range(T)):
                live=1-dones[t];delta=rewards[t]+.99*nextv*live-values[t]
                gae=delta+.99*.95*live*gae;advantages[t],nextv=gae,values[t]
            returns=(advantages+values).flatten();adv=advantages.flatten();adv=(adv-adv.mean())/(adv.std()+1e-8)
        torch.cuda.synchronize();now=time.perf_counter();timings['gae_s']=now-phase;phase=now
        finite=torch.ones((),dtype=torch.bool,device='cuda')
        with torch.cuda.nvtx.range('ppo'):
            for _ in range(4):
                for inds in torch.randperm(T*B,device='cuda').split(4096):
                    dist,v=model(observations.flatten(0,1)[inds],masks.flatten(0,1)[inds])
                    ratio=(dist.log_prob(actions.flatten()[inds])-oldlp.flatten()[inds]).exp()
                    pg=-torch.minimum(ratio*adv[inds],ratio.clamp(.8,1.2)*adv[inds]).mean()
                    loss=pg+.25*(v-returns[inds]).square().mean()-.01*dist.entropy().mean()
                    if args.mode=='baseline':
                        assert torch.isfinite(loss).item()
                    else:finite.logical_and_(torch.isfinite(loss))
                    opt.zero_grad(set_to_none=True);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),.5);opt.step()
        assert finite.item()
        torch.cuda.synchronize();now=time.perf_counter();timings['ppo_s']=now-phase;timings['total_s']=now-start
        return timings
    for _ in range(args.warmup):update()
    if args.nsys:torch.cuda.profiler.start()
    ctx=torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) if args.torch_profile else contextlib.nullcontext()
    with ctx as prof:
        rows=[update() for _ in range(args.updates)]
    if args.nsys:torch.cuda.profiler.stop()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.torch_profile:
        prof.export_chrome_trace(str(args.output.with_suffix('.trace.json')))
        args.output.with_suffix('.operators.txt').write_text(prof.key_averages().table(sort_by='self_cuda_time_total',row_limit=40))
    result=dict(mode=args.mode,library=str(lib),updates=rows,median={k:statistics.median(r[k] for r in rows) for k in rows[0]},
                gpu=torch.cuda.get_device_name(),torch=torch.__version__,decisions_per_update=T*B,
                final_parameters_finite=bool(all(torch.isfinite(p).all().item() for p in model.parameters())))
    result['decisions_per_second']=T*B/result['median']['total_s']
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='updates'}))
if __name__=='__main__':main()
