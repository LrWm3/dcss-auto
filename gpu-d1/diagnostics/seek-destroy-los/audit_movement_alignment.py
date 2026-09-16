"""Describe sampled movement during adjacency; no policy modifications."""
import hashlib,json,pathlib
import torch
from run_components import ROOT,Env,Policy,DIRS,adjacent_targets

@torch.no_grad()
def main():
 torch.set_num_threads(1);torch.distributions.Distribution.set_default_validate_args(False)
 suite=ROOT/'learning-runs/vision15-rest-sleep';m=json.loads((suite/'manifest.json').read_text());job=next(j for j in m['jobs'] if j['id']=='rest-seed0')
 lib=pathlib.Path(job['eval_library']);assert hashlib.sha256(lib.read_bytes()).hexdigest()==lib.with_suffix('.sha256').read_text().strip()
 ckpt=suite/'runs/rest-seed0/latest.pt';saved=torch.load(ckpt,map_location='cpu',weights_only=False);model=Policy(job['architecture'],job['width']).cuda();model.load_state_dict(saved['model']);model.eval()
 env=Env(1024,24,seed=900000,corpus=pathlib.Path(m['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=lib,limit=2048)
 torch.manual_seed(900000);active=torch.ones(1024,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(env.out);rows=[];dirs=torch.tensor(DIRS,device='cuda')
 for step in range(2048):
  if not active.any():break
  dist,_=model(env.obs,env.mask);probs=dist.probs;action=dist.sample();top=probs.argmax(-1);obs=env.obs
  adj,_=adjacent_targets(obs,env.mask);moving=(action<8)&~adj.gather(1,action.clamp(max=7)[:,None]).squeeze(1);select=active&adj.any(-1)&moving
  valid_move=(env.mask[:,:8]>0)&~adj
  route=obs[:,725:733];hasroute=route.any(-1);route_d=route.argmax(-1)
  # At frontier anchor, the observation instead supplies a first unknown neighbor.
  probe=(obs[:,718]>0)&~hasroute&(obs[:,719]==0)&(obs[:,720]==0)
  probe_d=((obs[:,723,None]==dirs[:,0])&(obs[:,724,None]==dirs[:,1])).long().argmax(-1)
  cue=torch.where(hasroute,route_d,probe_d);hascue=hasroute|probe
  cue_movable=hascue&valid_move.gather(1,cue[:,None]).squeeze(1)
  move=dirs[action.clamp(max=7)];cuevec=dirs[cue]
  dot=(move*cuevec).sum(-1);norm=(move.float().norm(dim=1)*cuevec.float().norm(dim=1))
  cos=dot/norm;matches=action==cue
  chance=1/valid_move.sum(-1).clamp(min=1)
  chance_aligned=(((dirs[None,:,:]*cuevec[:,None,:]).sum(-1)>0)&valid_move).sum(-1)/valid_move.sum(-1).clamp(min=1)
  rec=obs[:,450:650].reshape(-1,40,5);visible=rec[:,:,4]>0
  delta=torch.stack([(rec[:,:,0]*80).round(),(rec[:,:,1]*70).round()],-1)
  adjacent=visible&(delta.abs().amax(-1)==1)
  new_delta=delta-move[:,None,:]
  # Static-enemy geometry: would this step remove the player from current attack reach?
  after_adj=(visible&(new_delta.abs().amax(-1)<=1)).sum(-1);before_adj=adjacent.sum(-1)
  new_nearest=new_delta.abs().amax(-1).masked_fill(~visible,999).amin(-1)
  centroid=(delta*adjacent[:,:,None]).sum(1);enemy_dot=(move*centroid).sum(-1)
  pmove=(probs[:,:8]*valid_move).sum(-1)
  cue_conditional=probs.gather(1,cue[:,None]).squeeze(1)/pmove.clamp(min=1e-30)
  topmove=(top<8)&~adj.gather(1,top.clamp(max=7)[:,None]).squeeze(1)
  entries=torch.stack([torch.arange(1024,device='cuda'),torch.full((1024,),step+1,device='cuda'),obs[:,650]*18,before_adj,hasroute,probe,hascue,cue_movable,matches,cos,chance,chance_aligned,enemy_dot,after_adj,new_nearest,action,top,topmove,top==cue,probs.max(-1).values,cue_conditional,obs[:,721]*150],1)
  rows.append(entries[select]);env.step(action,active=active);ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended];active&=~ended
 assert not active.any();a=torch.cat(rows).cpu();ep=a[:,0].long();death=terminal[:,6].cpu()[ep]>0
 ref=json.loads((ROOT/'results/los-model-waiting-only.json').read_text())['results']['learned-sampled']['metrics']
 assert int(terminal[:,2].sum())==ref['clears'] and int(terminal[:,6].sum())==ref['deaths'] and float(terminal[:,5].mean())==ref['turns']
 def summarize(mask):
  b=a[mask];cue=b[:,7]>0;route=cue&(b[:,4]>0);probe=cue&(b[:,5]>0);top=cue&(b[:,17]>0)
  def mean(col,sel):return float(b[sel,col].mean()) if sel.any() else None
  return dict(n=len(b),has_route=int((b[:,4]>0).sum()),has_anchor_probe=int((b[:,5]>0).sum()),movable_cue_states=int(cue.sum()),exact_route_match=mean(8,route),exact_probe_match=mean(8,probe),exact_cue_match=mean(8,cue),uniform_legal_move_exact_chance=mean(10,cue),toward_cue_fraction=float((b[cue,9]>0).float().mean()),uniform_legal_move_toward_chance=mean(11,cue),opposite_cue_fraction=float((b[cue,9]<0).float().mean()),perpendicular_cue_fraction=float((b[cue,9]==0).float().mean()),greedy_movement_states=int(top.sum()),greedy_move_exact_cue_match=mean(18,top),mean_conditional_move_probability_on_cue=mean(20,cue),away_adjacent_centroid_fraction=float((b[:,12]<0).float().mean()),toward_adjacent_centroid_fraction=float((b[:,12]>0).float().mean()),perpendicular_or_balanced_centroid_fraction=float((b[:,12]==0).float().mean()),reduce_static_adjacent_count_fraction=float((b[:,13]<b[:,3]).float().mean()),increase_static_adjacent_count_fraction=float((b[:,13]>b[:,3]).float().mean()),leave_all_current_visible_enemies_reach_fraction=float((b[:,14]>1).float().mean()),direction_counts={str(DIRS[d]):int((b[:,15]==d).sum()) for d in range(8)})
 groups={'all_adjacent_moves':torch.ones(len(a),dtype=torch.bool),'one_adjacent':a[:,3]==1,'multiple_adjacent':a[:,3]>=2,'hp_le_6':a[:,2]<=6,'eventual_death':death,'confident_greedy_move':(a[:,17]>0)&(a[:,19]>=.8),'frontier_matching':(a[:,7]>0)&(a[:,8]>0),'frontier_not_matching':(a[:,7]>0)&(a[:,8]==0)}
 report=dict(checkpoint_sha256=hashlib.sha256(ckpt.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),library_sha256=hashlib.sha256(lib.read_bytes()).hexdigest(),seed=900000,episodes=1024,groups={k:summarize(v) for k,v in groups.items()},interpretation='Decision-weighted sampled directional moves during adjacency. Cue match restricted to available legal non-attack cue directions. Enemy geometry freezes enemies before their response; not actual escape success. Uniform-legal-move reference describes geometry, not an evaluated random policy.')
 (ROOT/'results/los-movement-alignment.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['groups']),flush=True)
if __name__=='__main__':main()
