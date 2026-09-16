"""Matched imitation PPO with a tiny physical-turn penalty, no entropy bonus."""
import fcntl,json,pathlib,subprocess,sys,time
from assets import ROOT,ASSETS
import run_ring_ablations as runner
SOURCE=ROOT/'learning-runs/autoregressive-imitation-no-entropy'
SUITE=ROOT/'learning-runs/autoregressive-turn-cost'
def plan():
 old=json.loads((SOURCE/'manifest.json').read_text());job=dict(old['jobs'][0],id='turn-cost-seed0',name='turn-cost',turn_milli=-.01,turn_reward=-.00001,reward_scheme='clear_minus_turn_cost',train_library=str(ASSETS/'autoregressive-clump1.so'),eval_library=str(ASSETS/'autoregressive-clump0.so'))
 return dict(format='autoregressive-turn-cost-v1',corpus=old['corpus'],jobs=[job],sources={str(p.relative_to(runner.ROOT)):runner.digest(p) for sub in ['scripts','src'] for p in sorted((runner.ROOT/sub).iterdir()) if p.suffix in ['.py','.cu','.h']})
def without_reward(x):
 if isinstance(x,dict):return {k:without_reward(v) for k,v in x.items() if k!='shaped_return'}
 if isinstance(x,list):return [without_reward(v) for v in x]
 return x

def main():
 SUITE.mkdir(exist_ok=True);store=runner.Store(SUITE,2*runner.GIB,10*runner.GIB)
 with (SUITE/'.pipeline.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);start=time.monotonic();m=plan();job=m['jobs'][0]
  assert runner.digest(pathlib.Path(job['initial_model']))==job['initial_model_sha256']
  if (SUITE/'manifest.json').exists():assert json.loads((SUITE/'manifest.json').read_text())==m,'Plan/source drift'
  else:store.json('manifest.json',m)
  store.json('status.json',dict(status='training',started_at=time.time()))
  subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',job['id'],'--output',str(SUITE),'--max-disk-gb','2','--min-free-gb','10'],check=True)
  result=json.loads((SUITE/'runs'/job['id']/'result.json').read_text());curve=json.loads((SUITE/'runs'/job['id']/'curve.json').read_text())
  assert [r['decisions'] for r in curve]==[0,500224,1000448]
  reference=json.loads((ROOT/'results/autoregressive-imitation-no-entropy.json').read_text())['evaluations'][0]
  for mode in ['sampled','greedy']:assert without_reward(curve[0][mode])==without_reward(reference[mode]),'Initial behavior differs'
  output=dict(ppo=result,evaluations=curve,wall_seconds=time.monotonic()-start,change='Only reward changes: +1 clear minus .00001 per physical turn. Same imitation initialization, zero critic, PPO optimizer/settings, gamma=1, entropy=0.')
  (ROOT/'results/autoregressive-turn-cost.json').write_text(json.dumps(output,indent=2)+'\n');store.json('status.json',dict(status='complete',wall_seconds=output['wall_seconds']));print('Turn-cost PPO complete',flush=True)
if __name__=='__main__':main()
