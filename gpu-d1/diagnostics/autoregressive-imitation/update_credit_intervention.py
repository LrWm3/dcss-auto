"""Identical-batch interventions on the first damaging PPO update."""
import copy,json,pathlib,sys,time,torch
import episode_credit as ec
ROOT=ec.ROOT
from tactical_models import Policy

def main():
 torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
 from torch.distributions import Distribution
 Distribution.set_default_validate_args(False)
 m=json.loads((ROOT/'learning-runs/autoregressive-turn-cost/manifest.json').read_text());job=m['jobs'][0];corpus=pathlib.Path(m['corpus']);cp=torch.load(job['initial_model'],map_location='cpu',weights_only=False)['model']
 torch.manual_seed(0);model=Policy('d4_exact',128).cuda();model.load_state_dict(cp)
 env=ec.Env(64,24,seed=17,corpus=corpus/'train',map_limit=256,library_path=job['train_library'],limit=2048)
 data,roll=ec.collect(model,env,17);N=len(data['a']);assert N==33733
 raw=data['gae'];target=raw+data['v'];adv=(raw-raw.mean())/(raw.std()+1e-8)
 rng=torch.cuda.get_rng_state();start=time.monotonic()
 out=dict(rollout=roll,variants={},credit={})
 for kind,sel in [('move',data['a']<8),('attack',(data['a']>=8)&(data['a']<16)),('wait',data['a']==16),('rest',data['a']==17)]:
  out['credit'][kind]=dict(count=int(sel.sum()),positive_fraction=float((adv[sel]>0).float().mean()),raw_advantage_mean=float(raw[sel].mean()),normalized_advantage_mean=float(adv[sel].mean()),mean_chosen_probability=float(data['lp'][sel].exp().mean()),successful_episode_fraction=float((data['mc'][sel]>0).float().mean()))
 def save():
  out['seconds']=time.monotonic()-start;(ROOT/'results/autoregressive-update-credit-intervention.json').write_text(json.dumps(out,indent=2)+'\n')
 save()
 for variant in ['without_negative_nav','without_centering','shuffled_advantages']:
  model=Policy('d4_exact',128).cuda();model.load_state_dict(cp);torch.cuda.set_rng_state(rng)
  if variant=='actor_frozen_body':
   for p in model.body.parameters():p.requires_grad_(False)
  used_adv=adv.clone()
  if variant=='without_centering':used_adv=raw/(raw.std()+1e-8)
  if variant=='shuffled_advantages':
   with torch.random.fork_rng(devices=[0]):
    torch.manual_seed(123);used_adv=adv[torch.randperm(N,device='cuda')]
  opt=torch.optim.Adam(model.parameters(),lr=.00003 if 'lr10' in variant else .0003,eps=1e-5)
  for epoch in range(0 if 'transplant' in variant else 4):
   for idx in torch.randperm(N,device='cuda').split(4096):
    dist,value=model(data['o'][idx],data['mask'][idx]);ratio=(dist.log_prob(data['a'][idx])-data['lp'][idx]).exp();terms=-torch.minimum(ratio*used_adv[idx],ratio.clamp(.8,1.2)*used_adv[idx]);selection=torch.ones_like(terms)
    if variant=='without_negative_nav':selection=~((data['a'][idx]<8)&(adv[idx]<0))
    if variant=='negative_nav_only':selection=((data['a'][idx]<8)&(adv[idx]<0)).float()
    if variant=='positive_nav_only':selection=((data['a'][idx]<8)&(adv[idx]>0)).float()
    if variant=='nonnav_only':selection=(data['a'][idx]>=8).float()
    pg=(terms*selection).mean();vl=.25*(value-target[idx]).square().mean()
    if variant in ['critic_head_only','both_detach_critic']:
     n=len(idx);groups=torch.arange(8,device='cuda').repeat_interleave(n)
     with torch.no_grad():h=model.body(model.d4.observation(data['o'][idx].repeat(8,1),groups)).reshape(8,n,128).mean(0)
     value=model.critic(h).squeeze(1);vl=.25*(value-target[idx]).square().mean()
    loss=pg
    opt.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),.5);opt.step()
  if 'transplant' in variant:
   changed=torch.load(ROOT/'learning-runs/autoregressive-update-cause/actor_only.pt',weights_only=False)
   prefix={'body_transplant':'body.','heads_transplant':None,'first_layer_transplant':'body.0.','second_layer_transplant':'body.2.'}[variant]
   model.load_state_dict({k:(changed[k] if (not k.startswith('body.') if prefix is None else k.startswith(prefix)) else v.cuda()) for k,v in cp.items()})
  with torch.no_grad():
   changes={};
   for prefix in ['body','actor','direction','type_embedding','critic']:
    changes[prefix]=sum(float((v-cp[k].cuda()).square().sum()) for k,v in model.state_dict().items() if k.startswith(prefix))**.5
   logdelta=[]
   for idx in torch.arange(N,device='cuda').split(4096):
    q,_=model(data['o'][idx],data['mask'][idx]);logdelta.append(q.log_prob(data['a'][idx])-data['lp'][idx])
   z=torch.cat(logdelta)
  result=dict(evaluation=ec.evaluate(model,job,corpus,128),parameter_change_norm=changes,approx_kl=float((z.exp()-1-z).mean()))
  dest=ROOT/'learning-runs/autoregressive-update-cause';dest.mkdir(parents=True,exist_ok=True);torch.save(model.state_dict(),dest/f'{variant}.pt')
  out['variants'][variant]=result;save();print(variant,json.dumps(result),flush=True)
 out['status']='complete';save()
if __name__=='__main__':main()
