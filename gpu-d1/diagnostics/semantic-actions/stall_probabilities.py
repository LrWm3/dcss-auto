"""Inspect unchanged greedy rollouts; stall = at least 32 consecutive WAITs."""
import hashlib,json,pathlib,sys,time
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/semantic-clear-only-v1/scripts'))
from tactical_models import Policy
from learn_env_ring_multi import Env
NAMES=['attack','explore','engage','wait','rest']
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
@torch.no_grad()
def main():
 torch.set_num_threads(1);results={}
 for suite,key in [('semantic-clear-only-1m','clear-only-seed0'),('semantic-discount-1m','gamma1.0-seed0')]:
  start=time.monotonic();root=ROOT/'learning-runs'/suite
  manifest=json.loads((root/'manifest.json').read_text());j=next(j for j in manifest['jobs'] if j['id']==key)
  cp=root/'runs'/key/'latest.pt';saved=torch.load(cp,map_location='cpu',weights_only=False)
  model=Policy(j['architecture'],j['width']).cuda();model.load_state_dict(saved['model']);model.eval()
  lib=pathlib.Path(j['eval_library']);assert digest(lib)==lib.with_suffix('.sha256').read_text().strip()
  env=Env(1024,24,seed=900000,corpus=pathlib.Path(manifest['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=lib,limit=2048)
  active=torch.ones(1024,dtype=torch.bool,device='cuda');streak=torch.zeros(1024,device='cuda',dtype=torch.long);maximum=streak.clone();terminal=torch.zeros_like(env.out)
  records=[];examples={};chosen=[];previous=env.obs.clone()
  for step in range(2048):
   if not active.any():break
   dist,_=model(env.obs,env.mask);p=dist.probs;a=p.argmax(-1)
   assert bool(((env.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all())
   streak=torch.where(active&(a==3),streak+1,0);maximum=torch.maximum(maximum,streak)
   stalled=active&(streak>=32)
   sleep=env.obs[:,959:999];visible=(sleep!=0).sum(1);awake=(sleep<0).sum(1)
   change=(env.obs-previous).abs();change[:,651]=0 # exclude elapsed-time input
   if stalled.any():
    # Probabilities, masks, visible/awake counts, HP, ticks, non-time obs change.
    row=torch.cat([p,env.mask,visible[:,None],awake[:,None],env.obs[:,650:652],change.amax(1)[:,None]],1)
    records.append(row[stalled].cpu())
   if len(chosen)<4:
    for idx in torch.where(stalled)[0].tolist():
     if idx not in chosen:chosen.append(idx);examples[str(idx)]=[]
     if len(chosen)==4:break
   for idx in chosen:
    if active[idx] and (int(streak[idx]) in [32,64,128,256,512,1024,1536] or float(env.obs[idx,651])*2048>=2047):
     enemy=env.obs[idx,450:650].reshape(40,5);rows=[]
     for slot in torch.where(enemy[:,4]>0)[0].tolist():
      e=enemy[slot];rows.append(dict(dx=round(float(e[0])*80),dy=round(float(e[1])*70),hp=float(e[2])*16,awake=bool(sleep[idx,slot]<0)))
     examples[str(idx)].append(dict(decision=step,turn=round(float(env.obs[idx,651])*2048),hp_fraction=float(env.obs[idx,650]),wait_streak=int(streak[idx]),probabilities=dict(zip(NAMES,p[idx].tolist())),available=dict(zip(NAMES,env.mask[idx].bool().tolist())),enemies=rows))
   previous.copy_(env.obs);env.step(a,active=active)
   ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended];active&=~ended
  assert not active.any()
  t=terminal.cpu();historical=json.loads((root/'runs'/key/'result.json').read_text())['final']['greedy']
  outcomes={name:int(t[:,col].sum()) for name,col in [('clears',2),('deaths',6),('timeouts',7)]}
  for name,metric in [('clears','clear_rate'),('deaths','death_rate'),('timeouts','timeout_rate')]:assert outcomes[name]==round(historical[metric]*1024)
  r=torch.cat(records);wp=r[:,3];other=r[:,:5].clone();other[:,3]=0;gap=wp-other.max(1).values
  groups={}
  for label,sel in [('all',torch.ones(len(r),dtype=torch.bool)),('sleepers_only',(r[:,10]>0)&(r[:,11]==0)),('awake_visible',r[:,11]>0),('no_visible',r[:,10]==0)]:
   if not sel.any():continue
   z=r[sel];groups[label]=dict(decisions=int(sel.sum()),mean_probs=dict(zip(NAMES,z[:,:5].mean(0).tolist())),availability_fraction=dict(zip(NAMES,z[:,5:10].mean(0).tolist())))
  result=dict(outcomes=outcomes,episodes_with_stall=int((maximum>=32).sum()),stall_decisions=len(r),wait_probability_quantiles=dict(zip(['min','p10','median','p90','max'],torch.quantile(wp,torch.tensor([0.,.1,.5,.9,1.])).tolist())),wait_margin_quantiles=torch.quantile(gap,torch.tensor([0.,.5,1.])).tolist(),fraction_wait_over_90_percent=float((wp>.9).float().mean()),fraction_non_time_observation_unchanged=float((r[:,14]==0).float().mean()),groups=groups,examples=examples,checkpoint_sha256=digest(cp),library_sha256=digest(lib),seconds=time.monotonic()-start)
  results[key]=result;print(key,json.dumps({k:v for k,v in result.items() if k not in ['examples']}),flush=True)
 output=dict(definition='Greedy WAIT streak >=32 decisions; summaries weighted by stalled decisions, not episodes. Exact original 1024 validation placements; no intervention.',script_sha256=digest(pathlib.Path(__file__)),results=results)
 (ROOT/'results/semantic-stall-probabilities.json').write_text(json.dumps(output,indent=2)+'\n')
if __name__=='__main__':main()
