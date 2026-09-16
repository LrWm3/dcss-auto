"""Fresh 500K clear-only reward run, queued behind the matched 1M continuations."""
import fcntl,json,pathlib,subprocess,sys,time
from assets import ROOT,ASSETS
import run_ring_ablations as runner
SUITE=ROOT/'learning-runs/semantic-clear-only-500k'
def plan():
 old=json.loads((ROOT/'learning-runs/semantic-discount-500k/manifest.json').read_text());base=old['jobs'][1]
 job=dict(base,id='clear-only-seed0',name='clear-only',kill_milli=0,clear_milli=1000,death_milli=0,explore_milli=0,turn_milli=0,reward_scheme='clear_only',gamma=1.0,steps=500000,train_library=str(ASSETS/'gamma1.0-clump1.so'),eval_library=str(ASSETS/'gamma1.0-clump0.so'))
 return dict(format='semantic-clear-only-v1',jobs=[job],corpus=old['corpus'],sources={str(p.relative_to(runner.ROOT)):runner.digest(p) for sub in ['scripts','src'] for p in sorted((runner.ROOT/sub).iterdir()) if p.suffix in ['.py','.cu','.h']})
def main():
 SUITE.mkdir(parents=True,exist_ok=True);store=runner.Store(SUITE,2*runner.GIB,10*runner.GIB);start=time.monotonic()
 with (SUITE/'.pipeline.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);m=plan();path=SUITE/'manifest.json'
  if path.exists():assert json.loads(path.read_text())==m,'Source/plan drift'
  else:store.json('manifest.json',m)
  previous=ROOT/'learning-runs/semantic-discount-1m';store.json('status.json',dict(status='queued',after=str(previous),queued_at=time.time()))
  with (previous/'.pipeline.lock').open('a') as predecessor:
   fcntl.flock(predecessor,fcntl.LOCK_EX)
   assert json.loads((previous/'status.json').read_text())['status']=='complete','Previous run did not complete successfully'
  for job in m['jobs']:
   if (SUITE/'runs'/job['id']/'result.json').exists():continue
   store.json('status.json',dict(status='training',job=job['id'],started_at=time.time()));print('Starting',job['id'],flush=True)
   subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',job['id'],'--output',str(SUITE),'--max-disk-gb','2','--min-free-gb','10'],check=True)
  result=json.loads((SUITE/'runs/clear-only-seed0/result.json').read_text())
  assert result['decisions']==500224
  (ROOT/'results/semantic-clear-only-500k.json').write_text(json.dumps(result,indent=2)+'\n');store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Clear-only run complete',flush=True)
if __name__=='__main__':main()
