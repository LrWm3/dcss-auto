"""Replay early PPO updates and isolate actor, critic and entropy effects."""
import hashlib,json,pathlib,sys,time
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/autoregressive-imitation-v1/scripts'))
from tactical_models import Policy
from learn_env_ring_multi import Env
SUITE=ROOT/'learning-runs/autoregressive-imitation'
OUT=ROOT/'learning-runs/autoregressive-handoff-audit'

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def make_env(job,corpus,training,batch):
 return Env(batch,24,seed=17 if training else 900000,corpus=corpus/('train' if training else 'validation'),map_limit=256 if training else 32,map_filter=-1 if training else -2,library_path=job['train_library' if training else 'eval_library'])

@torch.no_grad()
def evaluate(model,env,seed):
 with torch.random.fork_rng(devices=[0]):
  torch.manual_seed(seed);env.reset(seed);active=torch.ones(env.batch,device='cuda',dtype=torch.bool);terminal=torch.zeros_like(env.out);reward=torch.zeros(env.batch,device='cuda');counts=torch.zeros(4,device='cuda');dur=torch.zeros(env.batch,device='cuda')
  for _ in range(2048):
   if not active.any():break
   dist,_=model(env.obs,env.mask);a=dist.sample();kind=torch.where(a<8,0,torch.where(a<16,1,a-14));counts+=torch.bincount(kind[active],minlength=4)
   env.step(a,active=active);reward+=active*env.out[:,0];dur+=active*env.out[:,26]
   assert torch.equal(env.out[:,0],env.out[:,40])
   ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended];active&=~ended
  assert not active.any() and torch.equal(reward,terminal[:,2]) and torch.equal(dur,terminal[:,5])
  return dict(episodes=env.batch,clears=int(terminal[:,2].sum()),deaths=int(terminal[:,6].sum()),timeouts=int(terminal[:,7].sum()),kills=float(terminal[:,3].mean()),turns=float(dur.mean()),actions=dict(zip(['move','attack','wait','rest'],(counts/env.batch).tolist())))

def main():
 torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
 from torch.distributions import Distribution
 Distribution.set_default_validate_args(False)
 OUT.mkdir(exist_ok=True);start=time.monotonic()
 manifest=json.loads((SUITE/'manifest.json').read_text());job=manifest['jobs'][0];corpus=pathlib.Path(manifest['corpus']);cp=SUITE/'imitation.pt';saved=torch.load(cp,map_location='cpu',weights_only=False)['model']
 for field in ['train_library','eval_library']:
  p=pathlib.Path(job[field]);assert digest(p)==p.with_suffix('.sha256').read_text().strip()
 model=Policy('d4_exact',128).cuda();model.load_state_dict(saved)
 frozen_env=make_env(job,corpus,True,512);frozen=evaluate(model,frozen_env,17);del frozen_env
 ev=make_env(job,corpus,False,128);baseline=evaluate(model,ev,900000)
 print('Frozen training',json.dumps(frozen),'Diagnostic baseline',json.dumps(baseline),flush=True)
 results=dict(checkpoint_sha256=digest(cp),script_sha256=digest(pathlib.Path(__file__)),frozen_training=frozen,diagnostic_baseline=baseline,variants={},notes='30 updates of 512x64 decisions per variant. Evaluation sampled on fixed 128 placements across 32 validation layouts. Evaluations preserve RNG. No final-policy selection or full-panel claim.')
 def persist():
  results['wall_seconds']=time.monotonic()-start
  (ROOT/'results/autoregressive-handoff-audit.json').write_text(json.dumps(results,indent=2)+'\n')
 persist()
 for variant in ['normal','no_entropy','value_only','policy_only']:
  torch.manual_seed(0);env=make_env(job,corpus,True,512);model=Policy('d4_exact',128).cuda();model.load_state_dict(saved);opt=torch.optim.Adam(model.parameters(),lr=.0003,eps=1e-5)
  T,B=64,512;o=torch.empty(T,B,999,device='cuda');m=torch.empty(T,B,18,device='cuda');a=torch.empty(T,B,device='cuda',dtype=torch.long)
  lp,v,r,done,adv=[torch.empty(T,B,device='cuda') for _ in range(5)];old_probs=torch.empty(T,B,18,device='cuda')
  history=[];results['variants'][variant]=history
  for update in range(1,31):
   tick=time.monotonic();clears=deaths=timeouts=turns=0
   with torch.no_grad():
    for t in range(T):
     o[t].copy_(env.obs);m[t].copy_(env.mask);dist,value=model(env.obs,env.mask);action=dist.sample();a[t]=action;lp[t]=dist.log_prob(action);v[t]=value;old_probs[t]=dist.probs
     assert env.mask.gather(1,action[:,None]).all()
     env.step(action);r[t]=env.out[:,40];done[t]=env.out[:,1]
     assert torch.equal(env.out[:,0],env.out[:,2]) and torch.equal(env.out[:,0],env.out[:,40])
     assert torch.equal(env.out[:,1],(env.out[:,2]+env.out[:,6]+env.out[:,7]).clamp_max(1))
     clears+=int(env.out[:,2].sum());deaths+=int(env.out[:,6].sum());timeouts+=int(env.out[:,7].sum());turns+=int(env.out[:,26].sum())
    _,nextv=model(env.obs,env.mask);gae=torch.zeros(B,device='cuda')
    for t in reversed(range(T)):
     live=1-done[t];delta=r[t]+nextv*live-v[t];gae=delta+.95*live*gae;adv[t]=gae;nextv=v[t]
    returns=(adv+v).flatten();rawadv=adv.flatten();norm=(rawadv-rawadv.mean())/(rawadv.std()+1e-8)
    preerror=0.
    for idx in torch.arange(T*B,device='cuda').split(4096):
     q,_=model(o.flatten(0,1)[idx],m.flatten(0,1)[idx]);preerror=max(preerror,float((q.log_prob(a.flatten()[idx])-lp.flatten()[idx]).abs().max()))
    assert preerror<2e-5,preerror
   sums=torch.zeros(4,device='cuda');batches=0
   for epoch in range(4):
    for idx in torch.randperm(T*B,device='cuda').split(4096):
     dist,value=model(o.flatten(0,1)[idx],m.flatten(0,1)[idx]);ratio=(dist.log_prob(a.flatten()[idx])-lp.flatten()[idx]).exp()
     pg=-torch.minimum(ratio*norm[idx],ratio.clamp(.8,1.2)*norm[idx]).mean();vl=.25*(value-returns[idx]).square().mean();entropy=.01*dist.entropy().mean()
     loss={'normal':pg+vl-entropy,'no_entropy':pg+vl,'value_only':vl,'policy_only':pg}[variant]
     assert torch.isfinite(loss)
     opt.zero_grad(set_to_none=True);loss.backward();gn=torch.nn.utils.clip_grad_norm_(model.parameters(),.5);opt.step()
     sums+=torch.stack((pg.detach(),vl.detach(),entropy.detach(),gn.detach()));batches+=1
   with torch.no_grad():
    kl=tv=flip=postentropy=clip=0.
    for idx in torch.arange(T*B,device='cuda').split(4096):
     q,_=model(o.flatten(0,1)[idx],m.flatten(0,1)[idx]);p=old_probs.flatten(0,1)[idx];z=q.probs
     kl+=float((p*(p.clamp_min(1e-30).log()-z.clamp_min(1e-30).log())).sum())
     tv+=float((p-z).abs().sum()/2);postentropy+=float(q.entropy().sum())
     oldtype=torch.stack([p[:,:8].sum(1),p[:,8:16].sum(1),p[:,16],p[:,17]],1).argmax(1)
     flip+=int((oldtype!=q.types.probs.argmax(1)).sum());rat=(q.log_prob(a.flatten()[idx])-lp.flatten()[idx]).exp();clip+=int(((rat<.8)|(rat>1.2)).sum())
   row=dict(update=update,decisions=update*T*B,rollout_clears=clears,rollout_deaths=deaths,rollout_timeouts=timeouts,physical_turns=turns,value_mean=float(v.mean()),value_min=float(v.min()),value_max=float(v.max()),return_mean=float(returns.mean()),advantage_mean=float(rawadv.mean()),advantage_std=float(rawadv.std()),reward_sum=float(r.sum()),pre_update_logprob_max_error=preerror,mean_losses=dict(zip(['policy','weighted_value','weighted_entropy','gradient_norm'],(sums/batches).tolist())),post_update_kl=kl/(T*B),probability_total_variation=tv/(T*B),type_argmax_flip_fraction=flip/(T*B),post_entropy=postentropy/(T*B),post_clip_fraction=clip/(T*B),update_seconds=time.monotonic()-tick)
   if update in [1,2,4,8,16,24,30]:row['evaluation']=evaluate(model,ev,900000)
   history.append(row);persist();print(variant,json.dumps(row),flush=True)
  del env,model,opt,o,m,a,lp,v,r,done,adv,old_probs
 results['status']='complete';persist()
if __name__=='__main__':main()
