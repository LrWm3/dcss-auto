"""Bounded, resumable 10M seed-0 autoregressive-action experiment."""
import fcntl,json,pathlib,subprocess,sys,time
from assets import ROOT,ASSETS
import run_ring_ablations as runner
SUITE=ROOT/'learning-runs/autoregressive-actions'
def plan():
 old=json.loads((ROOT/'learning-runs/vision15-rest-sleep/manifest.json').read_text());base=next(j for j in old['jobs'] if j['id']=='rest-seed0')
 job=dict(base,id='autoregressive-seed0',name='autoregressive',steps=10000000,budget_unit='physical_turns',action_interface='move_attack_wait_rest_conditioned_direction',discount_unit='physical_turns',train_library=str(ASSETS/'autoregressive-clump1.so'),eval_library=str(ASSETS/'autoregressive-clump0.so'))
 return dict(format='autoregressive-actions-v1',jobs=[job],corpus=old['corpus'],sources={str(p.relative_to(runner.ROOT)):runner.digest(p) for sub in ['scripts','src'] for p in sorted((runner.ROOT/sub).iterdir()) if p.suffix in ['.py','.cu','.h']})
def main():
 SUITE.mkdir(parents=True,exist_ok=True);store=runner.Store(SUITE,2*runner.GIB,10*runner.GIB);start=time.monotonic()
 with (SUITE/'.pipeline.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);m=plan();path=SUITE/'manifest.json'
  if path.exists():assert json.loads(path.read_text())==m,'Source/plan drift'
  else:store.json('manifest.json',m)
  for job in m['jobs']:
   if (SUITE/'runs'/job['id']/'result.json').exists():continue
   store.json('status.json',dict(status='training',job=job['id'],started_at=time.time()));print('Starting',job['id'],flush=True)
   subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',job['id'],'--output',str(SUITE),'--max-disk-gb','2','--min-free-gb','10'],check=True)
  result=json.loads((SUITE/'runs/autoregressive-seed0/result.json').read_text());(ROOT/'results/autoregressive-actions-training.json').write_text(json.dumps(result,indent=2)+'\n');store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Autoregressive-action experiment complete',flush=True)
if __name__=='__main__':main()
