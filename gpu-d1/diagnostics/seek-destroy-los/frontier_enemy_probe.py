"""Fixed-state frontier-input intervention and matched rollout evaluation."""
import hashlib,json,pathlib,time
import torch
from run_components import ROOT,Env,Policy,DIRS,adjacent_targets
MODES=['route_to_enemy','target_and_route_to_enemy','zero_frontier']

def edit_frontier(obs,adj,weak,mode):
 out=obs.clone();use=adj.any(-1);ids=use.nonzero().flatten()
 if mode=='zero_frontier':out[ids,718:733]=0
 else:
  out[ids,725:733]=0;out[ids,725+weak[ids]]=1
  if mode=='target_and_route_to_enemy':
   dirs=torch.tensor(DIRS,device=obs.device,dtype=obs.dtype);delta=dirs[weak[ids]]
   out[ids,718]=1;out[ids,719]=delta[:,0]/80;out[ids,720]=delta[:,1]/70;out[ids,721]=1/150
 return out

def tests():
 obs=torch.arange(3*999,dtype=torch.float32).reshape(3,999);adj=torch.zeros(3,8,dtype=torch.bool);adj[0,1]=1;weak=torch.tensor([1,0,0]);saved=obs.clone()
 for mode in MODES:
  edited=edit_frontier(obs,adj,weak,mode)
  assert torch.equal(obs,saved) and torch.equal(edited[1:],obs[1:])
  assert torch.equal(edited[:,:718],obs[:,:718]) and torch.equal(edited[:,733:],obs[:,733:])
  if mode=='zero_frontier':assert not edited[0,718:733].any()
  else:
   assert edited[0,726]==1 and edited[0,725:733].sum()==1
   if mode=='route_to_enemy':assert torch.equal(edited[:,:725],obs[:,:725])
   else:assert edited[0,718]==1 and edited[0,719]==1/80 and edited[0,720]==0 and edited[0,721]==1/150

@torch.no_grad()
def main():
 tests();torch.set_num_threads(1);torch.distributions.Distribution.set_default_validate_args(False)
 suite=ROOT/'learning-runs/vision15-rest-sleep';manifest=json.loads((suite/'manifest.json').read_text());job=next(j for j in manifest['jobs'] if j['id']=='rest-seed0')
 lib=pathlib.Path(job['eval_library']);assert hashlib.sha256(lib.read_bytes()).hexdigest()==lib.with_suffix('.sha256').read_text().strip()
 ckpt=suite/'runs/rest-seed0/latest.pt';saved=torch.load(ckpt,map_location='cpu',weights_only=False)
 model=Policy(job['architecture'],job['width']).cuda();model.load_state_dict(saved['model']);model.eval()
 env=Env(1024,24,seed=900000,corpus=pathlib.Path(manifest['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=lib,limit=2048)
 report=dict(checkpoint_sha256=hashlib.sha256(ckpt.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),library_sha256=hashlib.sha256(lib.read_bytes()).hexdigest(),seed=900000,episodes=1024,target_rule='lowest HP legal visible adjacent enemy; compass ties',results={})
 for mode in ['baseline']+MODES:
  env.reset(900000);torch.manual_seed(900000);active=torch.ones(1024,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(env.out);rows=[];start=time.monotonic()
  for step in range(2048):
   if not active.any():break
   adj,weak=adjacent_targets(env.obs,env.mask);attackmask=torch.cat([adj,torch.zeros(1024,2,dtype=torch.bool,device='cuda')],1)
   view=env.obs if mode=='baseline' else edit_frontier(env.obs,adj,weak,mode)
   dist,_=model(view,env.mask);action=dist.sample()
   if mode=='baseline':
    use=active&adj.any(-1)
    original=dist.probs;data=[adj.sum(-1).float(),env.obs[:,650]*18,((original.argmax(-1)<8)&adj.gather(1,original.argmax(-1).clamp(max=7)[:,None]).squeeze(1)).float()]
    for variant in ['baseline']+MODES:
     probs=original if variant=='baseline' else model(edit_frontier(env.obs,adj,weak,variant),env.mask)[0].probs
     top=probs.argmax(-1)
     data.extend([(probs*attackmask).sum(-1),probs.gather(1,weak[:,None]).squeeze(1),attackmask.gather(1,top[:,None]).squeeze(1).float(),(top==weak).float()])
    rows.append(torch.stack(data,1)[use])
   assert bool(((env.mask.gather(1,action[:,None]).squeeze(1)>0)|~active).all())
   env.step(action,active=active);ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended];active&=~ended
  assert not active.any();metrics=dict(clears=int(terminal[:,2].sum()),deaths=int(terminal[:,6].sum()),timeouts=int(terminal[:,7].sum()),turns=float(terminal[:,5].mean()),kills=float(terminal[:,3].mean()),evaluation_seconds=time.monotonic()-start)
  if mode=='baseline':
   reference=json.loads((ROOT/'results/los-model-waiting-only.json').read_text())['results']['learned-sampled']['metrics']
   for k in ['clears','deaths','timeouts','turns','kills']:assert metrics[k]==reference[k]
   a=torch.cat(rows).cpu();groups={'all_adjacent':torch.ones(len(a),dtype=torch.bool),'original_greedy_nonattack':a[:,2]==0,'original_attack_probability_below_half':a[:,3]<.5,'multiple_adjacent':a[:,0]>=2,'hp_le_6':a[:,1]<=6}
   paired={}
   for group,select in groups.items():
    b=a[select];paired[group]=dict(n=len(b),variants={})
    for k,variant in enumerate(['baseline']+MODES):
     off=3+4*k;delta=b[:,off]-b[:,3]
     paired[group]['variants'][variant]=dict(mean_attack_probability=float(b[:,off].mean()),mean_target_probability=float(b[:,off+1].mean()),greedy_attack_fraction=float(b[:,off+2].mean()),greedy_selected_target_fraction=float(b[:,off+3].mean()),mean_attack_probability_change=float(delta.mean()),median_attack_probability_change=float(delta.median()),attack_probability_rises_by_10pp_fraction=float((delta>=.1).float().mean()),attack_probability_falls_by_10pp_fraction=float((delta<=-.1).float().mean()))
   report['fixed_state_comparison']=paired
  report['results'][mode]=dict(metrics=metrics,episodes=[dict(clear=bool(o[2]),death=bool(o[6]),timeout=bool(o[7]),kills=int(o[3]),turns=int(o[5])) for o in terminal.cpu().tolist()]);print(mode,json.dumps(metrics),flush=True)
  if mode=='baseline':print(json.dumps(report['fixed_state_comparison']),flush=True)
  (ROOT/'results/los-frontier-enemy-probe.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
