"""Greedy navigation loops and type-first versus joint argmax comparison."""
import json,pathlib,sys,time,torch
ROOT=pathlib.Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'branches/autoregressive-imitation-v1/scripts'))
from tactical_models import Policy
from learn_env_ring_multi import Env
@torch.no_grad()
def main():
 torch.set_num_threads(1);root=ROOT/'learning-runs/autoregressive-imitation-no-entropy';j=json.loads((root/'manifest.json').read_text())['jobs'][0]
 corpus=ROOT/'fixtures/d1-corpus-388/validation';out={};start=time.monotonic()
 original=json.loads((ROOT/'results/autoregressive-imitation-no-entropy.json').read_text())['evaluations']
 for stage in [0,500224,1000448]:
  cp=root/'runs'/j['id']/'snapshots'/f'{stage:012d}.pt';model=Policy('d4_exact',128).cuda();model.load_state_dict(torch.load(cp,map_location='cpu',weights_only=False)['model']);model.eval()
  for mode in ['type_greedy','joint_greedy']:
   env=Env(1024,24,seed=900000,corpus=corpus,map_limit=32,map_filter=-2,library_path=j['eval_library']);active=torch.ones(1024,device='cuda',dtype=torch.bool);terminal=torch.zeros_like(env.out)
   prevxy=torch.full((1024,2),-100,device='cuda');prevobs=env.obs.clone();streak=torch.zeros(1024,device='cuda',dtype=torch.long);maxstreak=streak.clone();loops=torch.zeros_like(streak);selfmoves=streak.clone();moves=streak.clone();sameobs=streak.clone();examples=[]
   for step in range(2048):
    if not active.any():break
    obs=env.obs.clone();xy=torch.round(obs[:,652:654]*torch.tensor([80,70],device='cuda'));dist,_=model(obs,env.mask);a=dist.greedy() if mode=='type_greedy' else dist.probs.argmax(1)
    mask=env.mask.clone();env.step(a,active=active);ended=active&(env.out[:,1]>0)
    nextxy=torch.round(env.obs[:,652:654]*torch.tensor([80,70],device='cuda'));moving=active&(a<8);valid=moving&~ended
    two=valid&(nextxy==prevxy).all(1)&(nextxy!=xy).any(1);loops+=two;selfmoves+=valid&(nextxy==xy).all(1);moves+=moving
    streak=torch.where(two,streak+1,0);maxstreak=torch.maximum(maxstreak,streak)
    diff=(env.obs-prevobs).abs();diff[:,651]=0;sameobs+=two&(diff.amax(1)==0)
    if len(examples)<4:
     ids=torch.where(streak==8)[0].tolist()
     for i in ids:
      if any(e['episode']==i for e in examples):continue
      # Current observation and the previous observation are the two endpoints.
      examples.append(dict(episode=i,decision=step,turn=round(float(obs[i,651])*2048),xy=xy[i].tolist(),next_xy=nextxy[i].tolist(),action=int(a[i]),type_probs=dist.types.probs[i].tolist(),move_direction_probs=dist.directions.probs[i,0].tolist(),frontier_route=obs[i,725:733].tolist(),frontier_distance=float(obs[i,721])*150,seen_tiles=float(obs[i,958])*1024,visible_enemies=int((obs[i,959:]!=0).sum()),full_hp=bool(obs[i,650]==1),observation_repeats_except_time=bool(diff[i].max()==0)))
      if len(examples)>=4:break
    prevxy=xy;prevobs=obs;terminal[ended]=env.out[ended];active&=~ended
   assert not active.any()
   t=terminal.cpu();stats=dict(clears=int(t[:,2].sum()),deaths=int(t[:,6].sum()),timeouts=int(t[:,7].sum()),movement_decisions=int(moves.sum()),immediate_reversals=int(loops.sum()),blocked_or_stationary_move_decisions=int(selfmoves.sum()),reversals_with_identical_observation_except_time=int(sameobs.sum()),episodes_with_at_least_8_consecutive_reversals=int((maxstreak>=8).sum()),timeout_episodes_with_at_least_8_reversals=int(((maxstreak.cpu()>=8)&(t[:,7]>0)).sum()),examples=examples)
   if mode=='type_greedy':
    ref=next(r for r in original if r['decisions']==stage)['greedy'];assert stats['clears']==round(ref['clear_rate']*1024) and stats['timeouts']==round(ref['timeout_rate']*1024)
   out[f'{stage}_{mode}']=stats;print(stage,mode,json.dumps({k:v for k,v in stats.items() if k!='examples'}),flush=True)
   (ROOT/'results/autoregressive-navigation-audit.json').write_text(json.dumps(dict(results=out,seconds=time.monotonic()-start,definition='Immediate reversal: MOVE returns to previous decision position; streak>=8 identifies repeated two-square oscillation. Observation equality excludes elapsed time only.'),indent=2)+'\n')
if __name__=='__main__':main()
