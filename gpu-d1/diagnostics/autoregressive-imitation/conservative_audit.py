"""Replay early PPO updates and isolate actor, critic and entropy effects."""
import copy,hashlib,json,pathlib,sys,time
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/autoregressive-imitation-v1/scripts'))
from tactical_models import Policy
from learn_env_ring_multi import Env
SUITE=ROOT/'learning-runs/autoregressive-imitation'
OUT=ROOT/'learning-runs/autoregressive-conservative-audit'

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def make_env(job,corpus,training,batch):
 return Env(batch,24,seed=17 if training else 900000,corpus=corpus/('train' if training else 'validation'),map_limit=256 if training else 32,map_filter=-1 if training else -2,library_path=job['train_library' if training else 'eval_library'])

@torch.no_grad()
def evaluate(model,env,seed,greedy=False):
 with torch.random.fork_rng(devices=[0]):
  torch.manual_seed(seed);env.reset(seed);active=torch.ones(env.batch,device='cuda',dtype=torch.bool);terminal=torch.zeros_like(env.out);reward=torch.zeros(env.batch,device='cuda');counts=torch.zeros(4,device='cuda');dur=torch.zeros(env.batch,device='cuda')
  for _ in range(2048):
   if not active.any():break
   dist,_=model(env.obs,env.mask);a=dist.greedy() if greedy else dist.sample();kind=torch.where(a<8,0,torch.where(a<16,1,a-14));counts+=torch.bincount(kind[active],minlength=4)
   env.step(a,active=active);reward+=active*env.out[:,0];dur+=active*env.out[:,26]
   assert torch.equal(env.out[:,0],env.out[:,40])
   ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended];active&=~ended
  assert not active.any() and torch.equal(reward,terminal[:,2]) and torch.equal(dur,terminal[:,5])
  return dict(episodes=env.batch,clears=int(terminal[:,2].sum()),deaths=int(terminal[:,6].sum()),timeouts=int(terminal[:,7].sum()),kills=float(terminal[:,3].mean()),turns=float(dur.mean()),actions=dict(zip(['move','attack','wait','rest'],(counts/env.batch).tolist())))


def fit_critic(saved,job,corpus):
 torch.manual_seed(733);model=Policy('d4_exact',128).cuda();model.load_state_dict(saved)
 env=make_env(job,corpus,True,512);env.reset(733)
 active=torch.ones(512,device='cuda',dtype=torch.bool);terminal=torch.zeros_like(env.out);features=[];ids=[]
 start=time.monotonic()
 with torch.no_grad():
  for _ in range(2048):
   if not active.any():break
   dist,_=model(env.obs,env.mask)
   n=len(env.obs);groups=torch.arange(8,device='cuda').repeat_interleave(n)
   h=model.body(model.d4.observation(env.obs.repeat(8,1),groups)).reshape(8,n,128).mean(0)
   features.append(h[active].cpu());ids.append(torch.where(active)[0].cpu())
   env.step(dist.sample(),active=active);ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended];active&=~ended
  assert not active.any()
 x=torch.cat(features).cuda();eid=torch.cat(ids).cuda();y=terminal[eid,2];train=torch.where(eid<384)[0];test=torch.where(eid>=384)[0]
 for p in model.parameters():p.requires_grad_(False)
 for p in model.critic.parameters():p.requires_grad_(True)
 opt=torch.optim.Adam(model.critic.parameters(),lr=.001)
 with torch.no_grad():before=float((model.critic(x[test]).squeeze(1)-y[test]).square().mean())
 for _ in range(8):
  for idx in train[torch.randperm(len(train),device='cuda')].split(4096):
   loss=(model.critic(x[idx]).squeeze(1)-y[idx]).square().mean();opt.zero_grad();loss.backward();opt.step()
 with torch.no_grad():after=float((model.critic(x[test]).squeeze(1)-y[test]).square().mean())
 state={k:v.detach().clone() for k,v in model.state_dict().items()}
 for k,v in saved.items():
  if not k.startswith('critic.'):assert torch.equal(state[k].cpu(),v)
 fit=dict(episodes=512,clears=int(terminal[:,2].sum()),training_episode_ids='0..383',heldout_episode_ids='384..511',state_samples=len(x),heldout_state_weighted_mse_before=before,heldout_state_weighted_mse_after=after,seconds=time.monotonic()-start,actor_weights_unchanged=True)
 print('Critic fit',json.dumps(fit),flush=True);return state,fit

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
 ev=make_env(job,corpus,False,128);baseline=evaluate(model,ev,900000);greedy_baseline=evaluate(model,ev,900000,True)
 print('Frozen training',json.dumps(frozen),'Diagnostic baseline',json.dumps(baseline),flush=True)
 results=dict(checkpoint_sha256=digest(cp),script_sha256=digest(pathlib.Path(__file__)),frozen_training=frozen,diagnostic_baseline=baseline,greedy_baseline=greedy_baseline,variants={},notes='30 updates of 512x64 decisions per variant. Evaluation sampled on fixed 128 placements across 32 validation layouts. Evaluations preserve RNG. No final-policy selection or full-panel claim. Critic fit uses terminal success targets from frozen-policy training episodes, critic linear head only. KL variants reject and roll back any epoch exceeding .01 mean old-to-new KL on the full rollout, including optimizer state. Entropy disabled in all variants.')
 def persist():
  results['wall_seconds']=time.monotonic()-start
  (ROOT/'results/autoregressive-conservative-audit.json').write_text(json.dumps(results,indent=2)+'\n')
 persist()
 warm,fit=fit_critic(saved,job,corpus);results['critic_fit']=fit;persist()
 for variant in ['kl_only','warm_only','warm_kl']:
  torch.manual_seed(0);env=make_env(job,corpus,True,512);model=Policy('d4_exact',128).cuda();model.load_state_dict(warm if 'warm' in variant else saved);opt=torch.optim.Adam(model.parameters(),lr=.0003,eps=1e-5)
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
   accepted_epochs=0;rejected_epoch=False
   for epoch in range(4):
    before_model=copy.deepcopy(model.state_dict()) if 'kl' in variant else None
    before_opt=copy.deepcopy(opt.state_dict()) if 'kl' in variant else None
    for idx in torch.randperm(T*B,device='cuda').split(4096):
     dist,value=model(o.flatten(0,1)[idx],m.flatten(0,1)[idx]);ratio=(dist.log_prob(a.flatten()[idx])-lp.flatten()[idx]).exp()
     pg=-torch.minimum(ratio*norm[idx],ratio.clamp(.8,1.2)*norm[idx]).mean();vl=.25*(value-returns[idx]).square().mean();entropy=.01*dist.entropy().mean()
     loss=pg+vl
     assert torch.isfinite(loss)
     opt.zero_grad(set_to_none=True);loss.backward();gn=torch.nn.utils.clip_grad_norm_(model.parameters(),.5);opt.step()
     sums+=torch.stack((pg.detach(),vl.detach(),entropy.detach(),gn.detach()));batches+=1
    if 'kl' in variant:
     with torch.no_grad():
      fullkl=0.
      for idx in torch.arange(T*B,device='cuda').split(4096):
       q,_=model(o.flatten(0,1)[idx],m.flatten(0,1)[idx]);p=old_probs.flatten(0,1)[idx]
       fullkl+=float((p*(p.clamp_min(1e-30).log()-q.probs.clamp_min(1e-30).log())).sum())
     if fullkl/(T*B)>.01:
      model.load_state_dict(before_model);opt.load_state_dict(before_opt);rejected_epoch=True;break
    accepted_epochs+=1
   with torch.no_grad():
    kl=tv=flip=postentropy=clip=0.
    for idx in torch.arange(T*B,device='cuda').split(4096):
     q,_=model(o.flatten(0,1)[idx],m.flatten(0,1)[idx]);p=old_probs.flatten(0,1)[idx];z=q.probs
     kl+=float((p*(p.clamp_min(1e-30).log()-z.clamp_min(1e-30).log())).sum())
     tv+=float((p-z).abs().sum()/2);postentropy+=float(q.entropy().sum())
     oldtype=torch.stack([p[:,:8].sum(1),p[:,8:16].sum(1),p[:,16],p[:,17]],1).argmax(1)
     flip+=int((oldtype!=q.types.probs.argmax(1)).sum());rat=(q.log_prob(a.flatten()[idx])-lp.flatten()[idx]).exp();clip+=int(((rat<.8)|(rat>1.2)).sum())
   row=dict(accepted_epochs=accepted_epochs,rejected_epoch=rejected_epoch,update=update,decisions=update*T*B,rollout_clears=clears,rollout_deaths=deaths,rollout_timeouts=timeouts,physical_turns=turns,value_mean=float(v.mean()),value_min=float(v.min()),value_max=float(v.max()),return_mean=float(returns.mean()),advantage_mean=float(rawadv.mean()),advantage_std=float(rawadv.std()),reward_sum=float(r.sum()),pre_update_logprob_max_error=preerror,mean_losses=dict(zip(['policy','weighted_value','weighted_entropy','gradient_norm'],(sums/batches).tolist())),post_update_kl=kl/(T*B),probability_total_variation=tv/(T*B),type_argmax_flip_fraction=flip/(T*B),post_entropy=postentropy/(T*B),post_clip_fraction=clip/(T*B),update_seconds=time.monotonic()-tick)
   if update in [1,2,4,8,16,24,30]:
    row['evaluation']=evaluate(model,ev,900000)
    row['greedy_evaluation']=evaluate(model,ev,900000,True)
   history.append(row);persist();print(variant,json.dumps(row),flush=True)
  del env,model,opt,o,m,a,lp,v,r,done,adv,old_probs
 results['status']='complete';persist()
if __name__=='__main__':main()
