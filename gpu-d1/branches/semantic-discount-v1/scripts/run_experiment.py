"""Matched short gamma=.99 and gamma=1.0 seed-zero runs."""
import fcntl,json,pathlib,subprocess,sys,time
from assets import ROOT,ASSETS
import run_ring_ablations as runner
SUITE=ROOT/'learning-runs/semantic-discount-500k'
def plan():
 old=json.loads((ROOT/'learning-runs/semantic-actions/manifest.json').read_text());base=old['jobs'][0]
 jobs=[dict(base,id=f'gamma{g}-seed0',name=f'gamma{g}',gamma=g,steps=500000,checkpoint_every=250000,train_library=str(ASSETS/f'gamma{g}-clump1.so'),eval_library=str(ASSETS/f'gamma{g}-clump0.so')) for g in [.99,1.0]]
 return dict(format='semantic-discount-v1',jobs=jobs,corpus=old['corpus'],sources={str(p.relative_to(runner.ROOT)):runner.digest(p) for sub in ['scripts','src'] for p in sorted((runner.ROOT/sub).iterdir()) if p.suffix in ['.py','.cu','.h']})
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
  results={j['id']:json.loads((SUITE/'runs'/j['id']/'result.json').read_text()) for j in m['jobs']}
  initial=[json.loads((SUITE/'runs'/j['id']/'curve.json').read_text())[0] for j in m['jobs']]
  for mode in ['sampled','greedy']:assert initial[0][mode]==initial[1][mode],'Initial behavior differs between gamma conditions'
  (ROOT/'results/semantic-discount-500k.json').write_text(json.dumps(results,indent=2)+'\n')
  store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Both short runs complete',flush=True)
if __name__=='__main__':main()
