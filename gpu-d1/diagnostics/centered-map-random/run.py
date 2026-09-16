"""Read-only trajectory audit of random and learned full-map policies.

Uses the production simulator/library and held-out validation maps. No training.
Wall-blind control deliberately allows wall bumps; all other modes honor masks.
Wake/adjacency counts omit changes on the final transition (auto-reset), so are
lower bounds. Movement and kill counters include that transition explicitly.
"""
import argparse,json,pathlib,sys,time
import numpy as np
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/vision15-centered-map-v1/scripts'))
from learn_env_ring_multi import Env
from tactical_models import Policy

@torch.no_grad()
def run(args):
 torch.set_num_threads(1)
 manifest=json.loads((ROOT/'learning-runs/vision15-centered-map/manifest.json').read_text())
 job=manifest['jobs'][0]; n=args.episodes
 assert n%32==0
 env=Env(n,24,seed=900000,corpus=pathlib.Path(manifest['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=job['eval_library'])
 model=None
 if args.checkpoint:
  saved=torch.load(args.checkpoint,map_location='cpu',weights_only=False)
  model=Policy(job['architecture'],job['width']).cuda().to(memory_format=torch.channels_last)
  model.load_state_dict(saved['model']);model.fast_maps=True;model.eval()
 torch.manual_seed(900000)
 device='cuda';ids=torch.arange(n,device=device);active=torch.ones(n,dtype=torch.bool,device=device)
 scale=torch.tensor([80,70],device=device)
 def xy():return (env.obs[:,652:654]*scale).round().long()
 def records():
  r=env.obs[:,450:650].reshape(n,40,5)
  return (r[:,:,:2]*scale).round().long(),r[:,:,2]*16,r[:,:,4]>0,env.obs[:,959:999]
 start=xy(); rel,hp,alive,sleep=records();initial_abs=start[:,None,:]+rel
 initial_dist=rel.abs().amax(-1);initial_near=((initial_dist<=6)&alive).sum(-1)
 visited=torch.zeros((n,5600),dtype=torch.bool,device=device);visited[ids,start[:,1]*80+start[:,0]]=True
 everawake=torch.zeros_like(alive);everadjacent=torch.zeros_like(alive)
 counters={k:torch.zeros(n,device=device) for k in ['decisions','moves','attacks','hits','damage','waits','rests','rest_turns','rest_available','adjacent_decisions','attack_when_adjacent','legal_directions','max_displacement','killed_initially_near','rest_probability_sum','prob_uniform_abs_max_sum']}
 hist=torch.zeros(10,device=device); terminal=torch.zeros((n,env.out_size),device=device);prevkills=torch.zeros(n,device=device)
 # Compact traces stay local; JSON contains only representative episodes.
 trace=np.zeros((2048,n,7),dtype=np.int16);event_trace=[]
 started=time.monotonic();deltas=torch.tensor([[0,-1],[1,0],[0,1],[-1,0],[1,-1],[1,1],[-1,1],[-1,-1],[0,0],[0,0]],device=device)
 for tick in range(2048):
  live=active.nonzero().flatten()
  if not len(live):break
  pos=xy().clone();rel,hp,alive,sleep=records();hp=hp.clone();alive=alive.clone();sleep=sleep.clone()
  available=env.mask[:,9]>0
  if model:
   with torch.autocast('cuda',dtype=torch.float16):dist,_=model(env.obs[live],env.mask[live])
   probs=dist.probs
  else:
   weights=env.mask[live].clone()
   if args.mode=='wall_blind':weights[:,:8]=1
   if args.mode=='wait':weights.zero_();weights[:,8]=1
   probs=weights/weights.sum(-1,keepdim=True)
  action=torch.full((n,),8,device=device,dtype=torch.long)
  action[live]=torch.distributions.Categorical(probs=probs).sample()
  hist+=torch.bincount(action[live],minlength=10)
  uniform=env.mask[live]/env.mask[live].sum(-1,keepdim=True)
  counters['prob_uniform_abs_max_sum'][live]+=(probs-uniform).abs().amax(-1)
  counters['rest_probability_sum'][live]+=probs[:,9]
  destination=pos+deltas[action];direction=action<8
  target=((rel==deltas[action][:,None,:]).all(-1)&alive&direction[:,None])
  attack=target.any(-1)&active
  assert bool((target.sum(-1)<=1).all())
  adjacent=((rel.abs().amax(-1)==1)&alive).any(-1)
  everawake|=(sleep<0)&alive&active[:,None]
  everadjacent|=(rel.abs().amax(-1)==1)&alive&active[:,None]
  movement=direction&~attack&(env.mask.gather(1,action[:,None]).squeeze(1)>0)&active
  nextpos=torch.where(movement[:,None],destination,pos)
  visited[ids[active],(nextpos[:,1]*80+nextpos[:,0])[active]]=True
  displacement=(nextpos-start).abs().amax(-1)
  counters['max_displacement']=torch.maximum(counters['max_displacement'],displacement*active)
  for key,val in [('decisions',active),('moves',movement),('attacks',attack),('waits',(action==8)&active),('rests',(action==9)&active),('rest_available',available&active),('adjacent_decisions',adjacent&active),('attack_when_adjacent',attack&adjacent),('legal_directions',env.mask[:,:8].sum(-1)*active)]:counters[key]+=val
  old_active=active.clone()
  env.step(action,active=active)
  out=env.out
  ended=active&(out[:,1]>0)
  terminal[ended]=out[ended]
  delta_kills=torch.where(active,out[:,3]-prevkills,0)
  assert bool(((delta_kills==0)|(delta_kills==1)).all())
  assert bool((~(delta_kills>0)|attack).all()),'Kill without player attack'
  target_hp=(target*hp).sum(-1)
  assert bool((~(delta_kills>0)|(target_hp<=4)).all()),'Kill without sufficient damage'
  counters['killed_initially_near']+=delta_kills*(target&(initial_dist<=6)).any(-1)
  counters['rest_turns']+=out[:,35]*active
  # HP comparison before auto-reset; count terminal killing blows as hits.
  newhp=env.obs[:,450:650].reshape(n,40,5)[:,:,2]*16
  damage=(target*(hp-newhp)).sum(-1)
  damage=torch.where(ended,torch.where(delta_kills>0,target_hp,0),damage)*active
  counters['damage']+=damage.clamp_min(0)
  counters['hits']+=(damage>0)&attack
  assert bool((ended|~active|((hp>0).sum(-1)-(newhp>0).sum(-1)==delta_kills)).all())
  for ix in (0,1,2):
   if bool(delta_kills[ix]>0):
    slot=int(target[ix].long().argmax())
    event_trace.append(dict(episode=ix,decision=tick+1,turn=int(out[ix,5]),player=nextpos[ix].tolist(),enemy_initial=initial_abs[ix,slot].tolist(),enemy_start_distance=int(initial_dist[ix,slot]),kills=int(out[ix,3])))
  trace[tick,:,:2]=nextpos.cpu().numpy();trace[tick,:,2]=action.cpu().numpy();trace[tick,:,3]=out[:,3].cpu().numpy();trace[tick,:,4]=out[:,4].cpu().numpy();trace[tick,:,5]=old_active.cpu().numpy();trace[tick,:,6]=out[:,5].cpu().numpy()
  prevkills=torch.where(active,out[:,3],prevkills)
  active&=~ended
  if tick%512==0:print(args.label,'decision',tick,'active',len(live),flush=True)
 assert not bool(active.any())
 counts={k:v.cpu().numpy() for k,v in counters.items()}
 kills=terminal[:,3].cpu().numpy()
 result=dict(label=args.label,mode=args.mode,checkpoint=args.checkpoint,episodes=n,maps=32,env_seed=900000,action_seed=900000,seconds=time.monotonic()-started,config=list(env.config),
  clear_rate=float(terminal[:,2].mean()),death_rate=float(terminal[:,6].mean()),timeout_rate=float(terminal[:,7].mean()),kills=float(kills.mean()),turns=float(terminal[:,5].mean()),
  means={k:float(v.mean()) for k,v in counts.items()},unique_tiles=float(visited.sum(-1).float().mean()),initial_enemies_within_wake_radius=float(initial_near.float().mean()),initial_has_enemy_within_wake_radius=float((initial_near>0).float().mean()),
  enemies_ever_awake_lower_bound=float(everawake.sum(-1).float().mean()),enemies_ever_adjacent_lower_bound=float(everadjacent.sum(-1).float().mean()),action_histogram=hist.tolist(),
  rest_fraction_when_available=float(counts['rests'].sum()/max(1,counts['rest_available'].sum())),
  mean_max_probability_deviation_from_uniform=float(counts['prob_uniform_abs_max_sum'].sum()/counts['decisions'].sum()),
  kill_quantiles=np.quantile(kills,[0,.25,.5,.75,1]).tolist(),
  movement_quantiles=np.quantile(counts['max_displacement'],[0,.25,.5,.75,1]).tolist(),
  kill_validation='Every kill matched an attack on an adjacent enemy with <=4 HP; nonterminal kill deltas matched enemy HP disappearance.',
  limitations='Wake/adjacency omit final transition; hits/damage omit nonfatal damage on terminal death/timeout turns; diagnostics use AMP for both checkpoints.',examples=[])
 for ix in (0,1,2):
  length=int(counts['decisions'][ix]);last=trace[length-1,ix]
  result['examples'].append(dict(episode=ix,map_seed=env.metadata[ix%32]['seed'],start=start[ix].tolist(),end=last[:2].tolist(),kills=float(kills[ix]),initial_near=int(initial_near[ix]),unique_tiles=int(visited[ix].sum()),max_displacement=float(counts['max_displacement'][ix]),moves=float(counts['moves'][ix]),attacks=float(counts['attacks'][ix]),rests=float(counts['rests'][ix]),turns=int(last[6]),death=bool(terminal[ix,6]),kill_events=[v for v in event_trace if v['episode']==ix]))
 outdir=ROOT/'learning-runs/centered-map-random-audit';outdir.mkdir(exist_ok=True)
 np.savez_compressed(outdir/(args.label+'-traces.npz'),trace=trace[:tick+1])
 path=ROOT/'results'/('centered-map-random-'+args.label+'.json');path.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ('examples','config')}),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--mode',choices=['uniform','wall_blind','wait'],default='uniform');p.add_argument('--checkpoint');p.add_argument('--label',required=True);p.add_argument('--episodes',type=int,default=1024);run(p.parse_args())
