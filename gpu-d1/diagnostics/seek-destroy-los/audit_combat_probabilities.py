"""Inspect adjacent-combat probabilities and isolate combat-only sampling changes."""
import hashlib,json,pathlib,time
import torch
from torch.distributions import Categorical
from run_components import ROOT,Env,Policy,DIRS,adjacent_targets

COLUMNS=['episode','decision','hp','adjacent','p_attack','p_wait','p_move','p_rest','top_probability','top_is_attack','sample_is_attack','sample_is_wait','p_weakest','p_weakest_given_attack','best_attack_is_weakest','sample_attack_is_weakest','top_action','sample_action','x','y','p_N','p_E','p_S','p_W','p_NE','p_SE','p_SW','p_NW','p_idle','p_heal']

@torch.no_grad()
def main():
 torch.set_num_threads(1);torch.distributions.Distribution.set_default_validate_args(False)
 suite=ROOT/'learning-runs/vision15-rest-sleep';manifest=json.loads((suite/'manifest.json').read_text());job=next(j for j in manifest['jobs'] if j['id']=='rest-seed0')
 lib=pathlib.Path(job['eval_library']);assert hashlib.sha256(lib.read_bytes()).hexdigest()==lib.with_suffix('.sha256').read_text().strip()
 ckpt=suite/'runs/rest-seed0/latest.pt';saved=torch.load(ckpt,map_location='cpu',weights_only=False)
 model=Policy(job['architecture'],job['width']).cuda();model.load_state_dict(saved['model']);model.eval()
 env=Env(1024,24,seed=900000,corpus=pathlib.Path(manifest['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=lib,limit=2048)
 report=dict(checkpoint=str(ckpt),checkpoint_sha256=hashlib.sha256(ckpt.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),library_sha256=hashlib.sha256(lib.read_bytes()).hexdigest(),trained_decisions=saved['decisions'],episodes=1024,seed=900000,results={})
 for mode in ['sampled','adjacent_greedy','adjacent_temperature_half']:
  env.reset(900000);torch.manual_seed(900000);active=torch.ones(1024,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(env.out);end_decision=torch.zeros(1024,device='cuda');rows=[];start=time.monotonic()
  for step in range(2048):
   if not active.any():break
   dist,_=model(env.obs,env.mask);probs=dist.probs;adj,_=adjacent_targets(env.obs,env.mask);hasadj=adj.any(-1);top=probs.argmax(-1)
   if mode=='adjacent_temperature_half':
    action=Categorical(logits=torch.where(hasadj[:,None],dist.logits*2,dist.logits)).sample()
   else:
    action=dist.sample()
    if mode=='adjacent_greedy':action=torch.where(hasadj,top,action)
   if mode=='sampled':
    attack_mask=torch.cat([adj,torch.zeros((1024,2),device='cuda',dtype=torch.bool)],1)
    pa=(probs*attack_mask).sum(-1);pw=probs[:,8];pm=probs[:,:8].sum(-1)-pa
    # Treat all equal-minimum-HP targets as weakest, rather than counting compass ties as mistakes.
    rec=env.obs[:,450:650].reshape(-1,40,5);dx=(rec[:,:,0]*80).round();dy=(rec[:,:,1]*70).round()
    hp=torch.stack([torch.where((rec[:,:,4]>0)&(dx==x)&(dy==y),rec[:,:,2],float('inf')).amin(-1) for x,y in DIRS],1).masked_fill(~adj,float('inf'))
    weakest=adj&(hp==hp.amin(-1,keepdim=True));weakmask=torch.cat([weakest,torch.zeros((1024,2),device='cuda',dtype=torch.bool)],1)
    pweak=(probs*weakmask).sum(-1);bestattack=probs.masked_fill(~attack_mask,-1).argmax(-1)
    get=lambda mask,a:mask.gather(1,a[:,None]).squeeze(1).float()
    data=torch.stack([torch.arange(1024,device='cuda'),torch.full((1024,),step+1,device='cuda'),env.obs[:,650]*18,adj.sum(-1),pa,pw,pm,probs[:,9],probs.max(-1).values,get(attack_mask,top),get(attack_mask,action),(action==8).float(),pweak,pweak/pa.clamp(min=1e-30),get(weakmask,bestattack),get(weakmask,action),top,action,(env.obs[:,652]*80).round(),(env.obs[:,653]*70).round()],1)
    rows.append(torch.cat([data,probs],1)[active&hasadj])
   assert bool(((env.mask.gather(1,action[:,None]).squeeze(1)>0)|~active).all())
   env.step(action,active=active);ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended];end_decision[ended]=step+1;active&=~ended
  assert not active.any()
  metrics=dict(clears=int(terminal[:,2].sum()),deaths=int(terminal[:,6].sum()),timeouts=int(terminal[:,7].sum()),turns=float(terminal[:,5].mean()),kills=float(terminal[:,3].mean()),evaluation_seconds=time.monotonic()-start)
  result=dict(metrics=metrics,episodes=[dict(clear=bool(o[2]),death=bool(o[6]),timeout=bool(o[7]),kills=int(o[3]),turns=int(o[5])) for o in terminal.cpu().tolist()])
  if mode=='sampled':
   ref=json.loads((ROOT/'results/los-model-waiting-only.json').read_text())['results']['learned-sampled']['metrics']
   for k in ['clears','deaths','timeouts','turns','kills']:assert metrics[k]==ref[k]
   a=torch.cat(rows).cpu();ep=a[:,0].long();death=terminal[:,6].cpu()[ep]>0;clear=terminal[:,2].cpu()[ep]>0;last=end_decision.cpu()[ep]-a[:,1]
   def summary(mask):
    b=a[mask];n=len(b)
    if not n:return dict(n=0)
    nonattack=b[:,10]==0;multi=b[:,3]>=2;attacks=b[:,10]>0
    return dict(n=n,mean_p_attack=float(b[:,4].mean()),median_p_attack=float(b[:,4].median()),p_attack_quantiles=torch.quantile(b[:,4],torch.tensor([.1,.25,.5,.75,.9])).tolist(),mean_p_wait=float(b[:,5].mean()),mean_p_move=float(b[:,6].mean()),mean_p_rest=float(b[:,7].mean()),greedy_attacks_fraction=float(b[:,9].mean()),actual_attack_fraction=float(b[:,10].mean()),actual_wait_fraction=float(b[:,11].mean()),nonattack_count=int(nonattack.sum()),nonattack_with_attack_argmax=int((nonattack&(b[:,9]>0)).sum()),nonattack_with_p_attack_ge_90=int((nonattack&(b[:,4]>=.9)).sum()),confident_nonattack_argmax_ge_50=int(((b[:,9]==0)&(b[:,8]>=.5)).sum()),confident_nonattack_argmax_ge_80=int(((b[:,9]==0)&(b[:,8]>=.8)).sum()),multi_states=int(multi.sum()),multi_mean_p_weakest_given_attack=float(b[multi,13].mean()) if multi.any() else None,multi_best_attack_is_weakest=float(b[multi,14].mean()) if multi.any() else None,multi_sample_attack_is_weakest=float(b[multi&attacks,15].mean()) if (multi&attacks).any() else None)
   groups={'all':torch.ones(len(a),dtype=torch.bool),'one_adjacent':a[:,3]==1,'multiple_adjacent':a[:,3]>=2,'hp_le_6':a[:,2]<=6,'eventual_death':death,'eventual_clear':clear,'last_10_decisions_before_death':death&(last<10)}
   result['adjacent_probability_audit']={k:summary(v) for k,v in groups.items()}
   bins=[(0,.25),(.25,.5),(.5,.75),(.75,.9),(.9,1.00001)]
   result['attack_probability_bins']=[dict(low=lo,high=min(hi,1),**summary((a[:,4]>=lo)&(a[:,4]<hi))) for lo,hi in bins]
   result['nonattack_argmax_actions']={str(d):int((a[:,16]==d).logical_and(a[:,9]==0).sum()) for d in range(10)}
   examples={}
   for label,mask in [('confident_nonattack', (a[:,9]==0)&(a[:,8]>=.8)),('sampled_nonattack_despite_p_attack_90',(a[:,10]==0)&(a[:,4]>=.9)),('multi_target_disagreement',(a[:,3]>=2)&(a[:,14]==0))]:
    indices=mask.nonzero().flatten();chosen=[];seen=set()
    for idx in indices.tolist():
     episode=int(a[idx,0]);
     if episode in seen:continue
     seen.add(episode);chosen.append({k:float(v) for k,v in zip(COLUMNS,a[idx].tolist())}|dict(episode_death=bool(terminal[episode,6]),map_seed=env.metadata[episode%32]['seed']))
     if len(chosen)==8:break
    examples[label]=chosen
   result['examples']=examples
  report['results'][mode]=result
  print(mode,json.dumps(metrics),flush=True)
  if mode=='sampled':print(json.dumps(result['adjacent_probability_audit']),flush=True)
  (ROOT/'results/los-combat-probabilities.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
