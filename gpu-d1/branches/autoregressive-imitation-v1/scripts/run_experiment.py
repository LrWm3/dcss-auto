"""Bounded deterministic demonstrations -> behavioral cloning -> clear-only PPO."""
import fcntl,json,pathlib,subprocess,sys,time
import torch
from assets import ROOT,ASSETS
import run_ring_ablations as runner
from tactical_models import Policy
from learn_env_ring_multi import Env
SUITE=ROOT/'learning-runs/autoregressive-imitation'

def plan():
 old=json.loads((ROOT/'learning-runs/semantic-clear-only-500k/manifest.json').read_text())
 job=dict(old['jobs'][0],id='imitation-seed0',name='imitation',steps=1000000,train_library=str(ASSETS/'autoregressive-clump1.so'),eval_library=str(ASSETS/'autoregressive-clump0.so'),action_interface='move_attack_wait_rest_conditioned_direction')
 return dict(format='autoregressive-imitation-v1',corpus=old['corpus'],jobs=[job],demonstrations=524288,bc_epochs=8,bc_batch=2048,bc_lr=.0003,seed=0,sources={str(p.relative_to(runner.ROOT)):runner.digest(p) for sub in ['scripts','src'] for p in sorted((runner.ROOT/sub).iterdir()) if p.suffix in ['.py','.cu','.h']})

@torch.no_grad()
def evaluate_teacher(m):
 env=Env(1024,24,seed=900000,corpus=pathlib.Path(m['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=m['jobs'][0]['eval_library'])
 active=torch.ones(1024,device='cuda',dtype=torch.bool);terminal=torch.zeros_like(env.out);actions=torch.zeros(4,device='cuda');turns=torch.zeros(1024,device='cuda')
 for _ in range(2048):
  if not active.any():break
  a=env.heuristic().clone();assert ((env.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all()
  kind=torch.where(a<8,0,torch.where(a<16,1,a-14));actions+=torch.bincount(kind[active],minlength=4)
  env.step(a,active=active);turns+=active*env.out[:,26]
  ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended];active&=~ended
 assert not active.any()
 return dict(clears=int(terminal[:,2].sum()),deaths=int(terminal[:,6].sum()),timeouts=int(terminal[:,7].sum()),turns=float(turns.mean()),actions_per_episode=dict(zip(['move','attack','wait','rest'],(actions/1024).tolist())))

def imitate(m,store):
 torch.manual_seed(0);torch.set_num_threads(1)
 teacher=evaluate_teacher(m);print('Teacher',json.dumps(teacher),flush=True)
 env=Env(512,24,seed=7017,corpus=pathlib.Path(m['corpus'])/'train',map_limit=256,library_path=m['jobs'][0]['train_library'])
 n=m['demonstrations'];obs=torch.empty(n,999,device='cuda',dtype=torch.float16);mask=torch.empty(n,18,device='cuda',dtype=torch.bool);labels=torch.empty(n,device='cuda',dtype=torch.long)
 physical=clears=deaths=timeouts=0;start=time.monotonic()
 with torch.no_grad():
  for i in range(0,n,512):
   a=env.heuristic().clone();assert env.mask.gather(1,a[:,None]).all()
   obs[i:i+512]=env.obs;mask[i:i+512]=env.mask.bool();labels[i:i+512]=a
   env.step(a);physical+=int(env.out[:,26].sum());clears+=int(env.out[:,2].sum());deaths+=int(env.out[:,6].sum());timeouts+=int(env.out[:,7].sum())
 torch.cuda.synchronize();generation_seconds=time.monotonic()-start
 # No demonstration dataset is written to disk; bounded GPU buffers only.
 torch.manual_seed(0);model=Policy('d4_exact',128).cuda();opt=torch.optim.Adam(model.parameters(),lr=m['bc_lr'],eps=1e-5)
 history=[];start=time.monotonic()
 for epoch in range(m['bc_epochs']):
  loss_sum=correct=0
  for idx in torch.randperm(n,device='cuda').split(m['bc_batch']):
   dist,_=model(obs[idx].float(),mask[idx]);loss=-dist.log_prob(labels[idx]).mean()
   assert torch.isfinite(loss)
   opt.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),.5);opt.step()
   loss_sum+=float(loss)*len(idx);correct+=int((dist.greedy()==labels[idx]).sum())
  history.append(dict(epoch=epoch+1,nll=loss_sum/n,training_action_accuracy=correct/n));print('BC',json.dumps(history[-1]),flush=True)
 torch.cuda.synchronize();seconds=time.monotonic()-start
 model.critic.weight.data.zero_();model.critic.bias.data.zero_() # no value learning during BC
 state=dict(model={k:v.cpu() for k,v in model.state_dict().items()},bc_epochs=m['bc_epochs'])
 store.atomic('imitation.pt',lambda f:torch.save(state,f),16*runner.MIB)
 summary=dict(teacher_validation=teacher,demonstration_decisions=n,demonstration_turns=physical,demonstration_completed_episodes=dict(clears=clears,deaths=deaths,timeouts=timeouts),demonstration_action_counts=torch.bincount(labels,minlength=18).tolist(),generation_seconds=generation_seconds,bc_train_seconds=seconds,history=history)
 store.json('imitation.json',summary);return summary

def main():
 torch.set_num_threads(1);SUITE.mkdir(exist_ok=True);store=runner.Store(SUITE,2*runner.GIB,10*runner.GIB)
 with (SUITE/'.pipeline.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);m=plan();start=time.monotonic()
  if (SUITE/'plan.json').exists():assert json.loads((SUITE/'plan.json').read_text())==m
  else:store.json('plan.json',m)
  store.json('status.json',dict(status='demonstrations_and_imitation',started_at=time.time()))
  if not (SUITE/'imitation.json').exists():summary=imitate(m,store)
  else:summary=json.loads((SUITE/'imitation.json').read_text())
  job=m['jobs'][0];job.update(initial_model=str(SUITE/'imitation.pt'),initial_model_sha256=runner.digest(SUITE/'imitation.pt'))
  store.json('manifest.json',m);store.json('status.json',dict(status='imitation_validation_then_ppo',started_at=time.time()))
  subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',job['id'],'--output',str(SUITE),'--max-disk-gb','2','--min-free-gb','10'],check=True)
  result=json.loads((SUITE/'runs'/job['id']/'result.json').read_text());curve=json.loads((SUITE/'runs'/job['id']/'curve.json').read_text())
  assert result['decisions']==1000448
  output=dict(imitation=summary,ppo=result,evaluations=curve,wall_seconds=time.monotonic()-start)
  (ROOT/'results/autoregressive-imitation.json').write_text(json.dumps(output,indent=2)+'\n');store.json('status.json',dict(status='complete',wall_seconds=output['wall_seconds']));print('Imitation and PPO complete',flush=True)
if __name__=='__main__':main()
