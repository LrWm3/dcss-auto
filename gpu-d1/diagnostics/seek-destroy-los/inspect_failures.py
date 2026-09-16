"""Replay selected matched evaluation episodes without changing their RNG streams."""
import argparse,json,sys
import torch
import numpy as np
from collections import deque
from run_retreat import ROOT,Env,RetreatPolicy,EVENTS

SELECTED=[863,624,48,112,332,870]

def hall_diagnosis(terrain,player,enemies,halls):
 if not halls:return dict(known=0,reachable=0,destination_away=0,first_step_away=0)
 offsets=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]
 dist={tuple(player):0};q=deque([tuple(player)])
 while q:
  x,y=q.popleft()
  for dx,dy in offsets:
   p=(x+dx,y+dy)
   if 0<=p[0]<80 and 0<=p[1]<70 and terrain[p[1],p[0]]==1 and p not in dist:
    dist[p]=dist[(x,y)]+1;q.append(p)
 sx=sum(e['x']-player[0] for e in enemies if e['awake']);sy=sum(e['y']-player[1] for e in enemies if e['awake'])
 reachable=[tuple(p) for p in halls if tuple(p) in dist]
 away=[p for p in reachable if (p[0]-player[0])*sx+(p[1]-player[1])*sy<0]
 first_away=0
 for p in away:
  while dist[p]>1:
   p=next((p[0]+dx,p[1]+dy) for dx,dy in offsets if dist.get((p[0]+dx,p[1]+dy),65535)+1==dist[p])
  first_away+=int((p[0]-player[0])*sx+(p[1]-player[1])*sy<0)
 return dict(known=len(halls),reachable=len(reachable),destination_away=len(away),first_step_away=first_away)

def main():
 parser=argparse.ArgumentParser();parser.add_argument("--wait-for-awake",action="store_true");args=parser.parse_args()
 selected=[624,135,386,787,997,1008] if args.wait_for_awake else SELECTED
 torch.set_num_threads(1)
 manifest=json.loads((ROOT/'learning-runs/vision15-rest-sleep/manifest.json').read_text())
 job=next(j for j in manifest['jobs'] if j['id']=='rest-seed0')
 env=Env(1024,24,seed=900000,corpus=__import__('pathlib').Path(manifest['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=job['eval_library'],limit=2048)
 old=json.loads((ROOT/('results/los-hallway-wait-awake.json' if args.wait_for_awake else 'results/los-hallway-retreat.json')).read_text())['results']
 traces={}
 for enabled in [False,True]:
  name='privileged-'+('retreat' if enabled else 'control');env.reset(900000);policy=RetreatPolicy(env,True,enabled,wait_for_awake=args.wait_for_awake)
  active=torch.zeros(1024,dtype=torch.bool,device='cuda');active[selected]=True
  rows={i:[] for i in selected}
  for step in range(2048):
   if not active.any():break
   live=active[selected].cpu().tolist();obs=env.obs[selected].cpu().numpy();states=policy.state[selected].cpu().tolist()
   actions=policy(active);aa=actions[selected].cpu().tolist();known=policy.base.memory[selected].cpu().numpy();newstate=policy.state[selected].cpu().tolist()
   env.step(actions,active=active);ended=active&(env.out[:,1]>0);policy.after_step(ended)
   outs=env.out[selected].cpu().tolist();events=policy.events[selected].cpu().tolist()
   for j,i in enumerate(selected):
    if not live[j]:continue
    o=obs[j];x,y=round(float(o[652])*80),round(float(o[653])*70)
    enemies=[dict(x=x+round(float(o[450+5*k])*80),y=y+round(float(o[451+5*k])*70),hp=round(float(o[452+5*k])*16,3),kind=round(float(o[453+5*k])*5),awake=bool(o[959+k]<0)) for k in range(40) if o[454+5*k]>0]
    grid=[''.join('@' if (xx,yy)==(x,y) else ('A' if next(e for e in enemies if (e['x'],e['y'])==(xx,yy))['awake'] else 's') if any((e['x'],e['y'])==(xx,yy) for e in enemies) else {0:'?',1:'.',-1:'#'}[int(known[j,yy*80+xx])] if 0<=xx<80 and 0<=yy<70 else '#' for xx in range(x-8,x+9)) for yy in range(y-8,y+9)]
    terrain=known[j].reshape(70,80)
    neighbors=np.stack([terrain[1+dy:69+dy,1+dx:79+dx] for dx,dy in [(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]])
    halls=np.zeros((68,78),dtype=bool)
    for a,b in [(0,2),(1,3),(4,6),(5,7)]:
     wanted=np.full(8,-1);wanted[[a,b]]=1
     halls|=(neighbors==wanted[:,None,None]).all(0)&(terrain[1:69,1:79]==1)
    hall_xy=[[int(xx+1),int(yy+1)] for yy,xx in zip(*np.where(halls))]
    out=outs[j]
    rows[i].append(dict(hall_diagnosis=hall_diagnosis(terrain,[x,y],enemies,hall_xy) if events[j][7] else None,known_halls=hall_xy,decision=step+1,xy=[x,y],hp=round(float(o[650])*18,3),enemies=enemies,state_before=states[j],state_action=newstate[j],action=aa[j],events=[EVENTS[k] for k,v in enumerate(events[j]) if v],hp_after=out[4],turn_after=int(out[5]),kills=int(out[3]),ended=bool(out[1]),clear=bool(out[2]),death=bool(out[6]),grid=grid))
    if out[1]:
     prior=old[name]['episodes'][i]
     assert (bool(out[2]),int(out[3]),int(out[5]))==(prior['clear'],prior['kills'],prior['turns']),(name,i,out,prior)
   active&=~ended
  traces[name]=rows
 dest=ROOT/('results/los-hallway-wait-failure-traces.json' if args.wait_for_awake else 'results/los-hallway-failure-traces.json');dest.write_text(json.dumps(dict(selected=selected,traces=traces),separators=(',',':'))+'\n')
 print(dest)
if __name__=='__main__':main()
