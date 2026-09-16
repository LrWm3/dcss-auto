"""Frozen learned LOS navigation plus observation-only encounter heuristics."""
import hashlib,json,pathlib,time
import torch
from run_retreat import ROOT,Env,RetreatPolicy
from tactical_models import Policy

def gate_encounter(obs,engaged,active,trigger):
 records=obs[:,450:650].reshape(-1,40,5)
 visible=records[:,:,4]>0
 start=(visible&(obs[:,959:999]<0)).any(-1) if trigger=='awake' else visible.any(-1)
 return torch.where(active,(engaged|start)&visible.any(-1),engaged)

def test_gate():
 obs=torch.zeros(4,999);active=torch.tensor([True,True,True,False]);engaged=torch.tensor([False,False,True,True])
 obs[:2,454]=1;obs[0,959]=-1;obs[1,959]=1
 assert gate_encounter(obs,engaged,active,'awake').tolist()==[True,False,False,True]
 assert gate_encounter(obs,engaged,active,'visible').tolist()==[True,True,False,True]
 engaged[1]=True
 assert gate_encounter(obs,engaged,active,'awake')[1] # Sleeping remainder keeps encounter active.

@torch.no_grad()
def main():
 test_gate();torch.set_num_threads(1);torch.distributions.Distribution.set_default_validate_args(False)
 suite=ROOT/'learning-runs/vision15-rest-sleep';manifest=json.loads((suite/'manifest.json').read_text());job=next(j for j in manifest['jobs'] if j['id']=='rest-seed0')
 lib=pathlib.Path(job['eval_library']);assert hashlib.sha256(lib.read_bytes()).hexdigest()==lib.with_suffix('.sha256').read_text().strip()
 checkpoint=suite/'runs/rest-seed0/latest.pt';saved=torch.load(checkpoint,map_location='cpu',weights_only=False)
 model=Policy(job['architecture'],job['width']).cuda();model.load_state_dict(saved['model']);model.eval()
 env=Env(1024,24,seed=900000,corpus=pathlib.Path(manifest['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=lib,limit=2048)
 previous=json.loads((suite/'runs/rest-seed0/result.json').read_text())['final']
 old_heuristic=json.loads((ROOT/'results/los-hallway-wait-awake.json').read_text())['results']['local-retreat']
 arms=[('learned','sampled'),('learned','greedy'),('awake','sampled'),('visible','sampled'),('awake','greedy'),('visible','greedy'),('heuristic','none')]
 report=dict(checkpoint=str(checkpoint),checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),trained_decisions=saved['decisions'],job=job,library_sha256=hashlib.sha256(lib.read_bytes()).hexdigest(),seed=900000,episodes_per_arm=1024,information='LOS observations only; no native privileged pursuit',source_sha256={name:hashlib.sha256(pathlib.Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ['run_hybrid.py','retreat_policy.py','retreat_policy.cu','local_policy.cu']},results={})
 for trigger,mode in arms:
  name=f'{trigger}-{mode}';env.reset(900000);torch.manual_seed(900000)
  policy=RetreatPolicy(env,False,True,wait_for_awake=True)
  active=torch.ones(1024,dtype=torch.bool,device='cuda');engaged=torch.zeros_like(active);terminal=torch.zeros_like(env.out)
  counts=torch.zeros((1024,5),device='cuda') # learned decisions, heuristic decisions, switches, rests, all decisions
  begin=time.monotonic()
  for decision in range(2048):
   if not active.any():break
   if trigger=='heuristic':use=active.clone()
   elif trigger=='learned':use=torch.zeros_like(active)
   else:
    new=gate_encounter(env.obs,engaged,active,trigger);counts[:,2]+=(new&~engaged&active);engaged=new;use=engaged&active
   if trigger!='heuristic':
    dist,_=model(env.obs,env.mask)
    learned=dist.sample() if mode=='sampled' else dist.probs.argmax(-1)
   # Update terrain memory and retreat state only when their ownership permits it.
   # Memory is always observed; no retreat may silently start during learned navigation.
   policy.base(active)
   heuristic=policy(use)
   actions=heuristic if trigger=='heuristic' else torch.where(use,heuristic,learned)
   policy.pending&=use
   # No-visible-enemy handoff resets retreat lockout, even when the heuristic is inactive.
   visible=(env.obs[:,450:650].reshape(-1,40,5)[:,:,4]>0).any(-1)
   reset=active&~visible;policy.state[reset,0]=0;policy.state[reset,1]=-1
   assert bool(((env.mask.gather(1,actions[:,None]).squeeze(1)>0)|~active).all())
   counts[:,0]+=active&~use;counts[:,1]+=use;counts[:,3]+=active&(actions==9);counts[:,4]+=active
   env.step(actions,active=active);ended=active&(env.out[:,1]>0);policy.after_step(ended)
   terminal[ended]=env.out[ended];active&=~ended
  assert not active.any();clear=terminal[:,2]>0
  metrics=dict(clears=int(clear.sum()),deaths=int(terminal[:,6].sum()),timeouts=int(terminal[:,7].sum()),clear_rate=float(clear.float().mean()),death_rate=float(terminal[:,6].mean()),timeout_rate=float(terminal[:,7].mean()),kills=float(terminal[:,3].mean()),turns=float(terminal[:,5].mean()),clear_only_turns=float(terminal[clear,5].mean()),learned_decisions=float(counts[:,0].mean()),heuristic_decisions=float(counts[:,1].mean()),encounters=float(counts[:,2].mean()),rest_uses=float(counts[:,3].mean()),decisions=float(counts[:,4].mean()),evaluation_seconds=time.monotonic()-begin)
  if trigger=='learned':
   for k in ['clear_rate','death_rate','timeout_rate','turns','kills']:assert metrics[k]==previous[mode][k],(name,k,metrics[k],previous[mode][k])
  if trigger=='heuristic':
   for k in ['clear_rate','death_rate','timeout_rate','turns','kills']:assert metrics[k]==old_heuristic['metrics'][k],(name,k)
  report['results'][name]=dict(metrics=metrics,episodes=[dict(map_seed=env.metadata[i%32]['seed'],clear=bool(clear[i]),death=bool(terminal[i,6]),timeout=bool(terminal[i,7]),kills=int(terminal[i,3]),turns=int(terminal[i,5])) for i in range(1024)])
  print(name,json.dumps(metrics),flush=True)
  (ROOT/'results/los-navigation-heuristic-combat.json').write_text(json.dumps(report,separators=(',',':'))+'\n')
if __name__=='__main__':main()
