"""Restart PPO from preserved imitation; change only entropy bonus to zero."""
import fcntl,json,pathlib,subprocess,sys,time
from assets import ROOT
import run_ring_ablations as runner
SOURCE=ROOT/'learning-runs/autoregressive-imitation'
SUITE=ROOT/'learning-runs/autoregressive-imitation-no-entropy'
def main():
 SUITE.mkdir(exist_ok=True);store=runner.Store(SUITE,2*runner.GIB,10*runner.GIB)
 with (SUITE/'.pipeline.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);start=time.monotonic()
  old=json.loads((SOURCE/'manifest.json').read_text());job=dict(old['jobs'][0],id='imitation-no-entropy-seed0',name='imitation-no-entropy',entropy=0.)
  assert runner.digest(pathlib.Path(job['initial_model']))==job['initial_model_sha256']
  m=dict(format='autoregressive-imitation-no-entropy',corpus=old['corpus'],jobs=[job],sources={str(p.relative_to(runner.ROOT)):runner.digest(p) for sub in ['scripts','src'] for p in sorted((runner.ROOT/sub).iterdir()) if p.suffix in ['.py','.cu','.h']})
  if (SUITE/'manifest.json').exists():assert json.loads((SUITE/'manifest.json').read_text())==m,'Plan/source drift'
  else:store.json('manifest.json',m)
  store.json('status.json',dict(status='training',started_at=time.time()))
  subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',job['id'],'--output',str(SUITE),'--max-disk-gb','2','--min-free-gb','10'],check=True)
  result=json.loads((SUITE/'runs'/job['id']/'result.json').read_text());curve=json.loads((SUITE/'runs'/job['id']/'curve.json').read_text())
  assert [r['decisions'] for r in curve]==[0,500224,1000448]
  reference=json.loads((ROOT/'results/autoregressive-imitation.json').read_text())['evaluations'][0]
  assert curve[0]['sampled']==reference['sampled'] and curve[0]['greedy']==reference['greedy'],'Initial validation differs'
  output=dict(ppo=result,evaluations=curve,wall_seconds=time.monotonic()-start,change='Entropy coefficient 0 instead of .01; fresh optimizer from identical preserved imitation weights; all other training settings unchanged.')
  (ROOT/'results/autoregressive-imitation-no-entropy.json').write_text(json.dumps(output,indent=2)+'\n');store.json('status.json',dict(status='complete',wall_seconds=output['wall_seconds']));print('No-entropy PPO complete',flush=True)
if __name__=='__main__':main()
