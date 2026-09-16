"""Frozen sampled-policy screen separating encounter-rule components."""
import hashlib,json,pathlib,time
import torch
from torch.distributions import Categorical
from run_hybrid import ROOT,Env,RetreatPolicy,Policy,waiting_override
DIRS=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]

def adjacent_targets(obs,mask):
 r=obs[:,450:650].reshape(-1,40,5);dx=(r[:,:,0]*80).round();dy=(r[:,:,1]*70).round()
 hp=torch.stack([torch.where((r[:,:,4]>0)&(dx==x)&(dy==y),r[:,:,2],float('inf')).amin(-1) for x,y in DIRS],1)
 valid=torch.isfinite(hp)&(mask[:,:8]>0);hp=hp.masked_fill(~valid,float('inf'))
 return valid,hp.argmin(-1)

def tests():
 o=torch.zeros(2,999);m=torch.ones(2,10)
 o[0,450:455]=torch.tensor([0.,-1/70,8/16,0,1]);o[0,455:460]=torch.tensor([1/80,0,3/16,0,1])
 adj,weak=adjacent_targets(o,m);assert adj[0].tolist()==[True,True,False,False,False,False,False,False] and weak[0]==1 and not adj[1].any()
 m[0,1]=0;adj,weak=adjacent_targets(o,m);assert weak[0]==0
 # Compass tie-break agrees with the local policy, regardless of record order.
 m[0,1]=1;o[0,452]=3/16;assert adjacent_targets(o,m)[1][0]==0

ARMS=[
 ('model',False,'none',False,False),('wait',True,'none',False,False),
 ('attack_model_target',False,'model',False,False),('attack_weakest',False,'weak',False,False),
 ('retarget_existing_attacks',False,'retarget',False,False),('retreat',False,'none',True,False),
 ('wait_attack_model_target',True,'model',False,False),('wait_attack_weakest',True,'weak',False,False),
 ('wait_retreat',True,'none',True,False),('attack_weakest_retreat',False,'weak',True,False),
 ('wait_attack_weakest_retreat',True,'weak',True,False),
 ('full_visible_encounter',True,'weak',True,True)]

@torch.no_grad()
def main():
 tests();torch.set_num_threads(1);torch.distributions.Distribution.set_default_validate_args(False)
 suite=ROOT/'learning-runs/vision15-rest-sleep';manifest=json.loads((suite/'manifest.json').read_text());job=next(j for j in manifest['jobs'] if j['id']=='rest-seed0')
 lib=pathlib.Path(job['eval_library']);assert hashlib.sha256(lib.read_bytes()).hexdigest()==lib.with_suffix('.sha256').read_text().strip()
 checkpoint=suite/'runs/rest-seed0/latest.pt';saved=torch.load(checkpoint,map_location='cpu',weights_only=False)
 model=Policy(job['architecture'],job['width']).cuda();model.load_state_dict(saved['model']);model.eval()
 env=Env(1024,24,seed=900000,corpus=pathlib.Path(manifest['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=lib,limit=2048)
 previous=json.loads((ROOT/'results/los-model-waiting-only.json').read_text())['results'];hybrid=json.loads((ROOT/'results/los-navigation-heuristic-combat.json').read_text())['results']
 report=dict(checkpoint=str(checkpoint),checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),trained_decisions=saved['decisions'],library_sha256=hashlib.sha256(lib.read_bytes()).hexdigest(),job=job,episodes=1024,seed=900000,mode='sampled',source_sha256={n:hashlib.sha256(pathlib.Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ['run_components.py','retreat_policy.cu','local_policy.cu']},results={})
 for name,wait,attack,retreat,pursue in ARMS:
  env.reset(900000);torch.manual_seed(900000);p=RetreatPolicy(env)
  active=torch.ones(1024,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(env.out);counts=torch.zeros((1024,5),device='cuda');start=time.monotonic()
  for _ in range(2048):
   if not active.any():break
   dist,_=model(env.obs,env.mask);adj,weak=adjacent_targets(env.obs,env.mask);hasadj=adj.any(-1)
   if attack=='model':
    allowed=torch.cat([adj,torch.zeros((1024,2),dtype=torch.bool,device='cuda')],1)
    # Still exactly one categorical sample per row per decision. Conditional on attack,
    # keep the model's relative action probabilities, rather than changing its target rule.
    logits=dist.logits.masked_fill(hasadj[:,None]&~allowed,-1e9)
    action=Categorical(logits=logits).sample()
   else:action=dist.sample()
   local=p.base(active).clone()
   visible=(env.obs[:,450:650].reshape(-1,40,5)[:,:,4]>0).any(-1)
   waiting=waiting_override(env.obs,active)
   if pursue:action=torch.where(visible&~hasadj&~waiting,local,action)
   if wait:action=torch.where(waiting,8,action)
   selected_attack=(action<8)&adj.gather(1,action.clamp(max=7)[:,None]).squeeze(1)
   if attack=='weak':action=torch.where(hasadj,weak,action)
   elif attack=='retarget':action=torch.where(selected_attack,weak,action)
   before=action.clone()
   p.before=env.obs[:,652:654].clone()
   if retreat:action=p.overlay(action,active)
   p.pending=active&(p.events[:,4]>0) if retreat else torch.zeros_like(active)
   assert bool(((env.mask.gather(1,action[:,None]).squeeze(1)>0)|~active).all())
   counts[:,0]+=active&(action==8);counts[:,1]+=active&(action<8)&adj.gather(1,action.clamp(max=7)[:,None]).squeeze(1);counts[:,2]+=active&(action==9);counts[:,3]+=active&(action!=before);counts[:,4]+=active
   env.step(action,active=active);ended=active&(env.out[:,1]>0);p.after_step(ended);terminal[ended]=env.out[ended];active&=~ended
  assert not active.any();clear=terminal[:,2]>0
  metrics=dict(clears=int(clear.sum()),deaths=int(terminal[:,6].sum()),timeouts=int(terminal[:,7].sum()),clear_rate=float(clear.float().mean()),death_rate=float(terminal[:,6].mean()),timeout_rate=float(terminal[:,7].mean()),kills=float(terminal[:,3].mean()),turns=float(terminal[:,5].mean()),clear_only_turns=float(terminal[clear,5].mean()),wait_actions=float(counts[:,0].mean()),attack_actions=float(counts[:,1].mean()),rest_uses=float(counts[:,2].mean()),retreat_changed_actions=float(counts[:,3].mean()),decisions=float(counts[:,4].mean()),evaluation_seconds=time.monotonic()-start)
  reference=previous['learned-sampled'] if name=='model' else previous['waiting-sampled'] if name=='wait' else hybrid['visible-sampled'] if name=='full_visible_encounter' else None
  if reference:
   for k in ['clear_rate','death_rate','timeout_rate','kills','turns']:assert metrics[k]==reference['metrics'][k],(name,k,metrics[k],reference['metrics'][k])
  report['results'][name]=dict(rules=dict(wait=wait,attack=attack,retreat=retreat,pursue_sleepers=pursue),metrics=metrics,episodes=[dict(map_seed=env.metadata[i%32]['seed'],clear=bool(clear[i]),death=bool(terminal[i,6]),timeout=bool(terminal[i,7]),kills=int(terminal[i,3]),turns=int(terminal[i,5])) for i in range(1024)])
  print(name,json.dumps(metrics),flush=True);(ROOT/'results/los-encounter-components.json').write_text(json.dumps(report,separators=(',',':'))+'\n')
if __name__=='__main__':main()
