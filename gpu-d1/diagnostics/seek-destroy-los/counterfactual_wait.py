"""Diagnostic one-action alternatives from exact simulator/RNG/policy snapshots.
This is hindsight search, not a deployable policy or a probability estimate.
"""
import json,pathlib
import torch
from run_retreat import ROOT,Env,RetreatPolicy
SELECTED=[624,135,386,787,997,1008]

def main():
 torch.set_num_threads(1)
 m=json.loads((ROOT/'learning-runs/vision15-rest-sleep/manifest.json').read_text());job=next(j for j in m['jobs'] if j['id']=='rest-seed0')
 env=Env(1024,24,seed=900000,corpus=pathlib.Path(m['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=job['eval_library'],limit=2048)
 prior=json.loads((ROOT/'results/los-hallway-wait-awake.json').read_text())['results']['privileged-retreat']['episodes']
 policy=RetreatPolicy(env,True,True,wait_for_awake=True)
 active=torch.zeros(1024,dtype=torch.bool,device='cuda');active[SELECTED]=True
 snapshots=[];seen=set()
 for decision in range(1,2049):
  if not active.any():break
  for i in SELECTED:
   if not active[i]:continue
   obs=env.obs[i];rec=obs[450:650].reshape(40,5);awake=int(((rec[:,4]>0)&(obs[959:999]<0)).sum());hp=round(float(obs[650])*18)
   stages=[]
   if decision==1:stages.append('initial')
   if awake>=2:stages.append('first_multiple_awake')
   if hp<=9:stages.append('first_half_hp')
   if hp<=9 and awake==0 and bool((rec[:,4]>0).any()):stages.append('low_hp_sleepers_only')
   dx=(rec[:,0]*80).round();dy=(rec[:,1]*70).round()
   if int(((rec[:,4]>0)&(dx.abs()<=1)&(dy.abs()<=1)&((dx!=0)|(dy!=0))).sum())>=2:stages.append('first_multiple_adjacent')
   for stage in stages:
    if (i,stage) in seen:continue
    seen.add((i,stage));snapshots.append(dict(episode=i,stage=stage,decision=decision,hp=hp,xy=[round(float(obs[652])*80),round(float(obs[653])*70)],state=env.state[i].clone(),obs=obs.clone(),mask=env.mask[i].clone(),memory=policy.base.memory[i].clone(),policy_state=policy.state[i].clone()))
  a=policy(active);env.step(a,active=active);ended=active&(env.out[:,1]>0);policy.after_step(ended)
  for i in SELECTED:
   if ended[i]:assert (int(env.out[i,3]),int(env.out[i,5]))==(prior[i]['kills'],prior[i]['turns'])
  active&=~ended
 # Each lane starts from an identical saved world/RNG state, then changes one action.
 candidates=[(snap,a) for snap in snapshots for a in [-1]+[a for a in range(10) if snap['mask'][a]>0]]
 assert len(candidates)<=env.batch
 env.reset(900000);policy=RetreatPolicy(env,True,True,wait_for_awake=True);active.zero_()
 for lane,(snap,_) in enumerate(candidates):
  env.state[lane]=snap['state'];env.obs[lane]=snap['obs'];env.mask[lane]=snap['mask'];policy.base.memory[lane]=snap['memory'];policy.state[lane]=snap['policy_state'];active[lane]=True
 outcomes={};baseline_actions={}
 for offset in range(2048):
  if not active.any():break
  actions=policy(active)
  if offset==0:
   for lane,(snap,a) in enumerate(candidates):
    baseline_actions[lane]=int(actions[lane])
    if a>=0:actions[lane]=a
   # after_step must track the movement actually selected, not an overridden retreat.
   changed=torch.zeros_like(active)
   for lane,(_,a) in enumerate(candidates):changed[lane]=a>=0 and a!=baseline_actions[lane]
   policy.pending&=~changed
  assert bool(((env.mask.gather(1,actions[:,None]).squeeze(1)>0)|~active).all())
  env.step(actions,active=active);ended=active&(env.out[:,1]>0);policy.after_step(ended)
  for lane in ended.nonzero().flatten().tolist():
   snap,a=candidates[lane];o=env.out[lane].tolist();outcomes[lane]=dict(episode=snap['episode'],stage=snap['stage'],decision=snap['decision'],start_hp=snap['hp'],xy=snap['xy'],override=a,baseline_action=baseline_actions[lane],clear=bool(o[2]),death=bool(o[6]),timeout=bool(o[7]),kills=int(o[3]),turns=int(o[5]))
   if a==-1:assert (bool(o[2]),int(o[3]),int(o[5]))==(prior[snap['episode']]['clear'],prior[snap['episode']]['kills'],prior[snap['episode']]['turns'])
  active&=~ended
 assert not active.any()
 report=dict(selected=SELECTED,method='Exact simulator RNG and policy snapshot; change one legal action then resume unchanged waiting+retreat policy. Baseline continuation must reproduce saved outcome. Hindsight-selected outcomes are not unbiased policy performance.',actions=['N','E','S','W','NE','SE','SW','NW','wait','rest'],outcomes=[outcomes[i] for i in range(len(candidates))])
 path=ROOT/'results/los-hallway-wait-counterfactual.json';path.write_text(json.dumps(report,indent=2)+'\n')
 for i in SELECTED:
  rows=[r for r in report['outcomes'] if r['episode']==i];wins=[r for r in rows if r['clear']]
  print(i,'clear alternatives',len(wins),'/',len(rows),'examples',wins[:3],flush=True)
if __name__=='__main__':main()
