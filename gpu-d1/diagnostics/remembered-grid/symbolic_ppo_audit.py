"""Weight provenance, gradient conflict, and eager/checkpoint swap diagnostics."""
import json,torch
from run import evaluate,save_json
from runtime import ROOT,OUT,Env,build
from optimize_symbolic import load
from symbolic_execution import PolicyExecution,StaticInference
from symbolic_ppo import collect,minibatch

def main():
 torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True;build()
 initial=load(True).configure_encoder(True,True);original={k:v.clone() for k,v in initial.state_dict().items()}
 report={'weights':{},'evaluations':{},'gradient':{}}
 for name in ['symbolic-ppo-seed0','symbolic-ppo-cause-critic_only','symbolic-ppo-cause-detached_critic','symbolic-ppo-cause-actor_only_retry']:
  ck=torch.load(OUT/name/'latest.pt',weights_only=False)['model']
  report['weights'][name]={prefix:sum(float((v-original[k]).square().sum()) for k,v in ck.items() if k.startswith(prefix))**.5 for prefix in ('local.','global_net.','tactical.','core.','policy.','value.')}
 # Crosses diagnose whether output-head changes alone account for the drift.
 trained=torch.load(OUT/'symbolic-ppo-seed0/latest.pt',weights_only=False)['model']
 for arm in ('original','ppo_eager','ppo_restore_policy_head','original_with_ppo_policy_head'):
  m=load(True).configure_encoder(True,True)
  if arm=='ppo_eager':state=trained
  elif arm=='ppo_restore_policy_head':state={k:(original[k] if k.startswith('policy.') else v) for k,v in trained.items()}
  elif arm=='original_with_ppo_policy_head':state={k:(trained[k] if k.startswith('policy.') else v) for k,v in original.items()}
  else:state=original
  m.load_state_dict(state);policy=StaticInference(PolicyExecution(m),amp=True,graphed=False)
  report['evaluations'][arm]=evaluate(policy,'test')['summary'];print(arm,report['evaluations'][arm],flush=True)
 # Same observations/advantages/hidden states for both loss-gradient components.
 m=load(True).configure_encoder(True,True);m.load_state_dict(torch.load(OUT/'symbolic-ppo-seed0/checkpoint-100000.pt',weights_only=False)['model'])
 execution=PolicyExecution(m);policy=StaticInference(execution,amp=True);data,h,n,_=collect(Env('train',128),m,policy,4321)
 ix=torch.arange(min(128,len(h)),device='cuda');grads={}
 for mode in ('actor_only','critic_only'):
  m.zero_grad(set_to_none=True);loss,_,_=minibatch(m,execution,data,h,ix,mode);(loss*1024).backward()
  grads[mode]={name:p.grad.detach().float().clone()/1024 for name,p in m.named_parameters()}
 for prefix in ('local.','global_net.','tactical.','core.','policy.','value.'):
  a=torch.cat([v.flatten() for k,v in grads['actor_only'].items() if k.startswith(prefix)])
  b=torch.cat([v.flatten() for k,v in grads['critic_only'].items() if k.startswith(prefix)])
  report['gradient'][prefix]=dict(actor_norm=float(a.norm()),critic_norm=float(b.norm()),cosine=float(torch.nn.functional.cosine_similarity(a[None],b[None])))
 print('gradient',report['gradient'],flush=True)
 # At initialization the supervised checkpoint's value head is exactly zero.
 report['initial_advantages']={}
 for lam in (.95,1.):
  torch.manual_seed(991);m=load(True).configure_encoder(True,True)
  policy=StaticInference(PolicyExecution(m),amp=True)
  data,h,n,summary=collect(Env('train',128),m,policy,777,lam)
  adv,ret,valid=data[-3:];won=(ret>0)&valid
  far=won&(ret<.1);near=won&(ret>.5)
  report['initial_advantages'][str(lam)]=dict(decisions=n,summary=summary,successful_decisions=int(won.sum()),negative_advantage_on_success_fraction=float((adv[won]<0).float().mean()),low_return_success_count=int(far.sum()),negative_low_return_success_fraction=float((adv[far]<0).float().mean()) if far.any() else None,near_success_count=int(near.sum()),return_min_success=float(ret[won].min()),return_mean_success=float(ret[won].mean()))
 print('initial advantages',report['initial_advantages'],flush=True)
 m=load(True).configure_encoder(True,True);m.load_state_dict(torch.load(OUT/'symbolic-ppo-seed0/checkpoint-100000.pt',weights_only=False)['model'])
 execution=PolicyExecution(m);policy=StaticInference(execution,amp=True)
 torch.manual_seed(992);short,h,_,_=collect(Env('train',128),m,policy,778,.95)
 torch.manual_seed(992);full,h,_,_=collect(Env('train',128),m,policy,778,1.)
 assert torch.equal(short[5],full[5]), 'Expected identical sampled trajectories'
 predictions=[]
 with torch.no_grad():
  for ids in torch.arange(len(h),device='cuda').split(128):
   with torch.autocast('cuda',dtype=torch.float16):
    x=execution.encode([v[ids].flatten(0,1) for v in full[:4]]).reshape(len(ids),16,-1)
    z,_=m.sequence(x,h[ids]);_,v=execution.heads(z,full[4][ids])
   predictions.append(v)
 v=torch.cat(predictions);valid=full[-1];target=full[-2][valid];pred=v[valid]
 gae=short[-2][valid];as_=short[-3][valid];af=full[-3][valid]
 report['value_at_100k']=dict(decisions=int(valid.sum()),mean_prediction=float(pred.mean()),mean_actual_discounted_return=float(target.mean()),mse=float((pred-target).square().mean()),explained_variance=float(1-(pred-target).var()/target.var()),gae_target_mean=float(gae.mean()),gae_target_mse_to_full=float((gae-target).square().mean()),normalized_advantage_sign_disagreement=float(((as_>0)!=(af>0)).float().mean()))
 print('value audit',report['value_at_100k'],flush=True)

 save_json(ROOT/'results/symbolic-ppo-cause-audit.json',report)
if __name__=='__main__':main()
