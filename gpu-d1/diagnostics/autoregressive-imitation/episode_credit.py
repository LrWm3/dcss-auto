"""Matched complete-episode collection: chunked GAE versus Monte Carlo PPO targets."""
import argparse,fcntl,hashlib,json,pathlib,sys,time
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/autoregressive-turn-cost-v1/scripts'))
from tactical_models import Policy
from learn_env_ring_multi import Env
from run_ring_ablations import Store,GIB,MIB

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def targets(r,v,done):
 """Time-major, padded terminal episodes. Gamma=1; padding excluded by caller."""
 mc=torch.zeros_like(r);gae=torch.zeros_like(r);future=torch.zeros_like(r[0]);g=future.clone()
 for t in reversed(range(len(r))):
  live=1-done[t];future=r[t]+live*future;mc[t]=future
  nextv=v[t+1] if t+1<len(r) else torch.zeros_like(v[t])
  if (t+1)%64==0:g=torch.zeros_like(g)
  g=r[t]+live*nextv-v[t]+.95*live*g;gae[t]=g
 return mc,gae

def selftest():
 r=torch.zeros(130,2);v=torch.zeros_like(r);done=torch.zeros_like(r)
 r[129,0]=1;done[129,0]=1;r[3,1]=1;done[3:,1]=1
 mc,gae=targets(r,v,done)
 assert torch.equal(mc[:,0],torch.ones(130)) and mc[0,1]==1 and mc[4,1]==0
 assert gae[0,0]==0 and gae[128,0]==.95 and gae[129,0]==1
 v.fill_(.3);mc,gae=targets(r,v,done)
 assert abs(float(gae[63,0]))<1e-6 and abs(float(gae[129,0])-.7)<1e-6
 # Direct forward reference, including a value bootstrap exactly at each chunk edge.
 for t in range(130):
  ref=torch.zeros(2);weight=torch.ones(2)
  for k in range(t,min(130,(t//64+1)*64)):
   nxt=v[k+1] if k+1<130 else torch.zeros(2)
   ref+=weight*(r[k]+(1-done[k])*nxt-v[k]);weight*=.95*(1-done[k])
  torch.testing.assert_close(ref,gae[t],atol=1e-6,rtol=1e-5)
 print('Target recurrence and terminal/chunk boundary tests passed',flush=True)

@torch.no_grad()
def collect(model,env,seed,greedy=False):
 env.reset(seed);B=env.batch;active=torch.ones(B,device='cuda',dtype=torch.bool)
 o=torch.empty(2048,B,999,device='cuda');mask=torch.empty(2048,B,18,device='cuda');a=torch.empty(2048,B,device='cuda',dtype=torch.long)
 v,r,d,lp,valid,rev=[torch.zeros(2048,B,device='cuda') for _ in range(6)]
 terminal=torch.zeros_like(env.out);ret=torch.zeros(B,device='cuda');turns=ret.clone();prev=torch.full((B,2),-999.,device='cuda');streak=torch.zeros(B,device='cuda');maxstreak=streak.clone()
 for t in range(2048):
  o[t]=env.obs;mask[t]=env.mask;valid[t]=active;dist,value=model(env.obs,env.mask);action=dist.greedy() if greedy else dist.sample()
  assert bool((env.mask.gather(1,action[:,None]).squeeze(1)>0).all())
  a[t]=action;v[t]=value;lp[t]=dist.log_prob(action);xy=env.obs[:,652:654].clone()
  env.step(action,active=active);ended=active&(env.out[:,1]>0)
  r[t]=env.out[:,40]*active;d[t]=(~active|ended).float();ret+=r[t];turns+=env.out[:,26]*active
  reverse=active&~ended&(action<8)&(env.obs[:,652:654]==prev).all(1)&(xy!=prev).any(1)
  rev[t]=reverse;streak=torch.where(reverse,streak+1,0);maxstreak=torch.maximum(streak,maxstreak);prev=xy
  terminal[ended]=env.out[ended];active&=~ended
  if not active.any():break
 assert not active.any();T=t+1
 torch.testing.assert_close(ret,terminal[:,2]-.00001*terminal[:,5],rtol=0,atol=2e-5)
 assert torch.equal(turns,terminal[:,5])
 mc,gae=targets(r[:T],v[:T],d[:T]);sel=valid[:T].bool()
 stats=dict(episodes=B,clears=int(terminal[:,2].sum()),deaths=int(terminal[:,6].sum()),timeouts=int(terminal[:,7].sum()),turns=float(turns.mean()),reward=float(ret.mean()),decisions=int(sel.sum()),physical_turns=int(turns.sum()),loop_episodes=int((maxstreak>=8).sum()),loop_timeouts=int(((maxstreak>=8)&(terminal[:,7]>0)).sum()),turns_by_outcome={name:float(terminal[terminal[:,col]>0,5].mean()) if (terminal[:,col]>0).any() else None for name,col in [('clear',2),('death',6),('timeout',7)]})
 data=dict(o=o[:T][sel],mask=mask[:T][sel],a=a[:T][sel],v=v[:T][sel],lp=lp[:T][sel],mc=mc[sel],gae=gae[sel],reverse=rev[:T][sel].bool())
 # Every start-of-episode MC return must equal its observed whole-episode reward.
 torch.testing.assert_close(mc[0],ret,atol=2e-5,rtol=0)
 return data,stats

@torch.no_grad()
def evaluate(model,job,corpus,batch):
 env=Env(batch,24,seed=900000,corpus=corpus/'validation',map_limit=32,map_filter=-2,library_path=job['eval_library'],limit=2048)
 out={}
 with torch.random.fork_rng(devices=[0]):
  for mode in ['sampled','greedy']:
   torch.manual_seed(900000);env.reset(900000);active=torch.ones(batch,device='cuda',dtype=torch.bool);terminal=torch.zeros_like(env.out);ret=torch.zeros(batch,device='cuda');prev=torch.full((batch,2),-999.,device='cuda');streak=torch.zeros(batch,device='cuda');maxstreak=streak.clone();counts=torch.zeros(4,device='cuda')
   for _ in range(2048):
    dist,_=model(env.obs,env.mask);action=dist.greedy() if mode=='greedy' else dist.sample();xy=env.obs[:,652:654].clone()
    kind=torch.where(action<8,0,torch.where(action<16,1,action-14));counts+=torch.bincount(kind[active],minlength=4)
    env.step(action,active=active);ret+=active*env.out[:,40];ended=active&(env.out[:,1]>0)
    reverse=active&~ended&(action<8)&(env.obs[:,652:654]==prev).all(1)&(xy!=prev).any(1)
    streak=torch.where(reverse,streak+1,0);maxstreak=torch.maximum(maxstreak,streak);prev=xy;terminal[ended]=env.out[ended];active&=~ended
    if not active.any():break
   assert not active.any();torch.testing.assert_close(ret,terminal[:,2]-.00001*terminal[:,5],rtol=0,atol=2e-5)
   out[mode]=dict(episodes=batch,clears=int(terminal[:,2].sum()),deaths=int(terminal[:,6].sum()),timeouts=int(terminal[:,7].sum()),turns=float(terminal[:,5].mean()),reward=float(ret.mean()),loop_episodes=int((maxstreak>=8).sum()),loop_timeouts=int(((maxstreak>=8)&(terminal[:,7]>0)).sum()),actions=dict(zip(['move','attack','wait','rest'],(counts/batch).tolist())),turns_by_outcome={name:float(terminal[terminal[:,col]>0,5].mean()) if (terminal[:,col]>0).any() else None for name,col in [('clear',2),('death',6),('timeout',7)]})
 return out

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--steps',type=int,default=1000000);ap.add_argument('--smoke',action='store_true');args=ap.parse_args()
 selftest();torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
 from torch.distributions import Distribution
 Distribution.set_default_validate_args(False)
 manifest=json.loads((ROOT/'learning-runs/autoregressive-turn-cost/manifest.json').read_text());job=manifest['jobs'][0];corpus=pathlib.Path(manifest['corpus']);cp=pathlib.Path(job['initial_model']);assert digest(cp)==job['initial_model_sha256']
 for field in ['train_library','eval_library']:
  p=pathlib.Path(job[field]);assert digest(p)==p.with_suffix('.sha256').read_text().strip()
 name='autoregressive-episode-credit'+('-smoke' if args.smoke else '');suite=ROOT/'learning-runs'/name;suite.mkdir(parents=True,exist_ok=True);store=Store(suite,2*GIB,10*GIB);lock=(suite/'.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 result=dict(status='running',checkpoint_sha256=digest(cp),script_sha256=digest(pathlib.Path(__file__)),reference_job=job,variants={},notes='Both conditions collect full episodes with frozen policy, same 64-world batches; differ only targets: GAE .95 reset each 64 decisions with value bootstrap, versus full remaining return minus old value. Gamma=1, entropy=0, same original tiny turn cost. Reset to fresh training placements every update. Updates use all valid decisions, no partial-episode truncation. This collection differs from the historical streaming PPO control. Final budget can overshoot to finish an episode batch. MC is a noisy sampled return, not counterfactual action quality.')
 start=time.monotonic()
 def save():
  result['wall_seconds']=time.monotonic()-start
  path=ROOT/'results'/f'{name}.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(result,indent=2)+'\n');tmp.replace(path)
 for variant in ['gae64','episode_return']:
  torch.manual_seed(0);model=Policy('d4_exact',128).cuda();model.load_state_dict(torch.load(cp,map_location='cpu',weights_only=False)['model']);opt=torch.optim.Adam(model.parameters(),lr=job['lr'],eps=1e-5)
  env=Env(8 if args.smoke else 64,24,seed=17,corpus=corpus/'train',map_limit=256,library_path=job['train_library'],limit=2048)
  history=[];result['variants'][variant]=dict(history=history);total=0;train_seconds=0.;update=0;next_eval=250000
  if not args.smoke:result['variants'][variant]['initial']=evaluate(model,job,corpus,128);save()
  while total<(100 if args.smoke else args.steps):
   store.ensure(128*MIB);tick=time.monotonic();data,roll=collect(model,env,17+update*1009);update+=1;N=len(data['a']);total+=N
   raw=data['gae'] if variant=='gae64' else data['mc']-data['v'];target=raw+data['v'];adv=(raw-raw.mean())/(raw.std()+1e-8)
   normalized={key:(x-x.mean())/(x.std()+1e-8) for key,x in [('gae',data['gae']),('mc',data['mc']-data['v'])]}
   row=dict(update=update,decisions=total,rollout=roll,value_mean=float(data['v'].mean()),mc_return_mean=float(data['mc'].mean()),gae_target_mse_vs_mc=float((data['gae']+data['v']-data['mc']).square().mean()),normalized_advantage_sign_agreement=float(((normalized['gae']>0)==(normalized['mc']>0)).float().mean()),reversal_decisions=int(data['reverse'].sum()))
   for key in ['gae','mc']:
    row[key+'_positive_reversal_advantage_fraction']=float((normalized[key][data['reverse']]>0).float().mean()) if data['reverse'].any() else None
   with torch.no_grad():
    errors=[]
    for idx in torch.arange(N,device='cuda').split(4096):
     dist,_=model(data['o'][idx],data['mask'][idx]);errors.append((dist.log_prob(data['a'][idx])-data['lp'][idx]).abs().max())
    assert max(float(x) for x in errors)<2e-5
   for _ in range(job['epochs']):
    for idx in torch.randperm(N,device='cuda').split(job['minibatch']):
     dist,value=model(data['o'][idx],data['mask'][idx]);ratio=(dist.log_prob(data['a'][idx])-data['lp'][idx]).exp();pg=-torch.minimum(ratio*adv[idx],ratio.clamp(.8,1.2)*adv[idx]).mean();loss=pg+.25*(value-target[idx]).square().mean()
     assert torch.isfinite(loss);opt.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),.5);opt.step()
   with torch.no_grad():
    delta=torch.empty(N,device='cuda')
    for idx in torch.arange(N,device='cuda').split(4096):
     dist,_=model(data['o'][idx],data['mask'][idx]);delta[idx]=dist.log_prob(data['a'][idx])-data['lp'][idx]
    row['positive_advantage_mean_logprob_change']=float(delta[adv>0].mean());row['negative_advantage_mean_logprob_change']=float(delta[adv<0].mean());row['reversal_mean_logprob_change']=float(delta[data['reverse']].mean()) if data['reverse'].any() else None
    row['approx_kl']=float((delta.exp()-1-delta).mean())
   torch.cuda.synchronize();train_seconds+=time.monotonic()-tick;row['train_seconds']=train_seconds;del data
   if update==1 or total>=next_eval or total>=args.steps or args.smoke:
    row['evaluation']=evaluate(model,job,corpus,32 if args.smoke else 1024 if total>=args.steps else 128)
    next_eval=(total//250000+1)*250000
    store.atomic(pathlib.Path(variant)/f'{total:012d}.pt',lambda f:torch.save(dict(model=model.state_dict(),decisions=total),f),16*MIB)
   history.append(row);save();print(variant,json.dumps(row),flush=True)
   store.atomic(pathlib.Path(variant)/'latest.pt',lambda f:torch.save(dict(model=model.state_dict(),optimizer=opt.state_dict(),decisions=total,update=update),f),32*MIB)
   if args.smoke:break
  del env,model,opt
 assert result['variants']['gae64']['history'][0]['rollout']==result['variants']['episode_return']['history'][0]['rollout'], 'First batch must match exactly'
 result['status']='complete';save();print('Episode credit experiment complete',flush=True)
if __name__=='__main__':main()
