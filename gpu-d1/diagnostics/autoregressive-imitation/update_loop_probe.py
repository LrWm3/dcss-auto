"""Capture both endpoints of new greedy loops and inspect identical-state logits."""
import json,pathlib,torch
import episode_credit as ec
ROOT=ec.ROOT
from tactical_models import Policy
@torch.no_grad()
def main():
 torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
 m=json.loads((ROOT/'learning-runs/autoregressive-turn-cost/manifest.json').read_text());j=m['jobs'][0]
 before=torch.load(j['initial_model'],map_location='cpu',weights_only=False)['model'];after=torch.load(ROOT/'learning-runs/autoregressive-update-cause/actor_only.pt',map_location='cpu',weights_only=False)
 states={'before':before,'after':after,'restore_first_layer':{k:before[k] if k.startswith('body.0.') else v for k,v in after.items()}}
 models={}
 for name,state in states.items():
  model=Policy('d4_exact',128).cuda();model.load_state_dict(state);models[name]=model
 env=ec.Env(128,24,seed=900000,corpus=pathlib.Path(m['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=j['eval_library'])
 active=torch.ones(128,device='cuda',dtype=torch.bool);prev=torch.full((128,2),-999.,device='cuda');streak=torch.zeros(128,device='cuda');previous_obs=env.obs.clone();previous_mask=env.mask.clone();cases=[];seen=set()
 for step in range(200):
  obs=env.obs.clone();mask=env.mask.clone();xy=obs[:,652:654].clone();d,_=models['after'](obs,mask);a=d.greedy();env.step(a,active=active);ended=active&(env.out[:,1]>0)
  reverse=active&~ended&(a<8)&(env.obs[:,652:654]==prev).all(1)&(xy!=prev).any(1);streak=torch.where(reverse,streak+1,0)
  for i in torch.where(streak==8)[0].tolist():
   if i in seen:continue
   seen.add(i);case=dict(episode=i,decision=step,endpoints=[])
   for o,ma in [(previous_obs[i:i+1],previous_mask[i:i+1]),(obs[i:i+1],mask[i:i+1])]:
    point=dict(xy=(o[0,652:654]*torch.tensor([80,70],device='cuda')).round().int().tolist(),frontier_route=o[0,725:733].tolist(),policies={})
    for name,model in models.items():
     q,_=model(o,ma);point['policies'][name]=dict(action=int(q.greedy()[0]),type_probs=q.types.probs[0].tolist(),move_probs=q.directions.probs[0,0].tolist())
    case['endpoints'].append(point)
   cases.append(case)
   if len(cases)>=8:break
  if len(cases)>=8:break
  prev=xy;previous_obs=obs;previous_mask=mask;active&=~ended
 (ROOT/'results/autoregressive-update-loop-probe.json').write_text(json.dumps(dict(cases=cases,note='Fixed observations at the two endpoints of loops induced by the first actor-only update; original, damaged, and first-layer-restored policy distributions. Direction indices N E S W NE SE SW NW.'),indent=2)+'\n')
 print(json.dumps(cases[:2],indent=2))
if __name__=='__main__':main()
