"""Scripted scenario checks and sampled policy evaluation; no action labels in training."""
import argparse,json,pathlib
import torch
from assets import ROOT,ASSETS
from tactical_env import TacticalEnv
from tactical_models import Policy
import run_ring_ablations as runner

@torch.no_grad()
def rollout(task,split,controller=None,model=None,batch=4096,seed=921000):
 env=TacticalEnv(batch,24,seed=seed,corpus=ASSETS/task/split,map_limit=16,map_filter=-2,library_path=ASSETS/'tactical.so')
 _,initial=env.probe(0);initial=initial.clone();active=torch.ones(batch,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(env.out)
 turns=torch.zeros(batch,device='cuda');waits=torch.zeros_like(turns);sleep_waits=torch.zeros_like(turns);woke=torch.zeros_like(active);wake_hp=torch.zeros_like(turns);first_probs=None
 if model is not None:
  dist,_=model(env.obs,env.mask);a,_=env.probe(0);a=a.clone();b,_=env.probe(1)
  first_probs=torch.stack([dist.probs.gather(1,a[:,None]).squeeze(1),dist.probs.gather(1,b[:,None]).squeeze(1),dist.probs[:,8]],1)
 torch.manual_seed(seed)
 for step in range(512):
  action,stats=env.probe(controller if controller is not None else 0)
  awake_before=stats[:,4].bool().clone()
  if model is not None:dist,_=model(env.obs,env.mask);action=dist.sample()
  waits+=active&(action==8);sleep_waits+=active&(action==8)&~awake_before;turns+=active
  env.step(action,active=active)
  ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended]
  _,after=env.probe(0)
  just_woke=active&~ended&~woke&after[:,4].bool()
  wake_hp[just_woke]=after[just_woke,0];woke|=just_woke
  active &= ~ended
  if not active.any():break
 def metrics(mask):
  count=int(mask.sum());d=dict(episodes=count)
  if not count:return d
  for key,x in [('clear',terminal[:,2]),('death',terminal[:,6]),('unresolved',active.float()),('turns',turns),('wait_turns',waits),('asleep_wait_turns',sleep_waits)]:d[key]=float(x[mask].mean())
  w=mask&woke;d['wake_hp']=float(wake_hp[w].mean()) if w.any() else None;d['wake_observed_rate']=float(woke[mask].float().mean())
  if first_probs is not None:
   p=first_probs[mask].mean(0).tolist()
   d['first_action_probabilities']=dict(zip(['attack_weak','attack_dangerous','wait'],p)) if task=='target' else dict(approach=p[0],wait=p[2])
  return d
 groups={}
 if task=='sleep':
  for health,hm in [('low',initial[:,0]<18),('full',initial[:,0]==18)]:
   for kind,km in [('weak',initial[:,3]>0),('dangerous',initial[:,2]>0)]:groups[health+'_'+kind]=metrics(hm&km)
 else:
  for key,m in [('equal_hp',initial[:,1]==initial[:,2]),('weak_wounded',initial[:,1]<initial[:,2]),('dangerous_wounded',initial[:,1]>initial[:,2])]:groups[key]=metrics(m)
 return dict(task=task,split=split,controller=controller,seed=seed,cap=512,overall=metrics(torch.ones_like(active)),groups=groups,initial_visible_rate=float(initial[:,11].mean()),initial_awake_rate=float(initial[:,4].mean()))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--checkpoint',type=pathlib.Path);ap.add_argument('--output',type=pathlib.Path,required=True);ap.add_argument('--controls',action='store_true');ap.add_argument('--batch',type=int,default=4096);args=ap.parse_args()
 torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
 if args.controls:
  report={}
  for task,modes in [('target',[0,1,2]),('sleep',[3,4])]:
   for split in ['train','heldout']:
    report[task+'/'+split]={str(mode):rollout(task,split,controller=mode,batch=args.batch) for mode in modes}
  args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
  for split in ['train','heldout']:
   sleep=report['sleep/'+split];a=sleep['3'];b=sleep['4']
   assert a['initial_visible_rate']==1 and a['initial_awake_rate']==0
   for kind in ['dangerous']:
    assert b['groups']['low_'+kind]['clear']>a['groups']['low_'+kind]['clear']+.1
    assert b['groups']['full_'+kind]==a['groups']['full_'+kind], 'At full HP, recover controller must behave identically'
   target=report['target/'+split]
   assert target['0']['groups']['weak_wounded']['clear']>target['1']['groups']['weak_wounded']['clear']+.05
   assert target['1']['groups']['equal_hp']['clear']>target['0']['groups']['equal_hp']['clear']+.05
  report['mechanism_checks_passed']=True
 else:
  ck=torch.load(args.checkpoint,map_location='cpu',weights_only=False);model=Policy(ck['job']['architecture'],ck['job']['width']).cuda().eval();model.load_state_dict(ck['model'])
  report=dict(checkpoint_sha256=runner.digest(args.checkpoint),decisions=ck['decisions'],tasks={task:rollout(task,'heldout',model=model,batch=args.batch) for task in ['target','sleep']})
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n');print('Evaluation complete',args.output,flush=True)
if __name__=='__main__':main()
