"""Wait for successful semantic completion, then run the autoregressive experiment."""
import fcntl,json,subprocess,sys,time
from run_experiment import SUITE,ROOT,plan
import run_ring_ablations as runner

def main():
 SUITE.mkdir(parents=True,exist_ok=True)
 with (SUITE/'.queue.lock').open('a') as own:
  fcntl.flock(own,fcntl.LOCK_EX|fcntl.LOCK_NB)
  store=runner.Store(SUITE,2*runner.GIB,10*runner.GIB)
  store.json('queued-plan.json',plan())
  store.json('status.json',dict(status='queued',after='semantic-actions',queued_at=time.time()))
  previous=ROOT/'learning-runs/semantic-actions'
  print('Waiting for semantic-actions to complete successfully.',flush=True)
  with (previous/'.pipeline.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   status=json.loads((previous/'status.json').read_text())
   if status['status']!='complete' or not (previous/'runs/semantic-seed0/result.json').exists():
    store.json('status.json',dict(status='blocked',reason='Predecessor exited without a completed result'))
    raise RuntimeError('Predecessor did not finish successfully; refusing to overlap/reorder experiments')
  assert json.loads((SUITE/'queued-plan.json').read_text())==plan(),'Queued source/plan drift'
  print('Semantic run complete; starting autoregressive experiment.',flush=True)
  try:subprocess.run([sys.executable,str(__import__('pathlib').Path(__file__).with_name('run_experiment.py'))],check=True)
  except Exception as e:
   store.json('status.json',dict(status='failed',error=str(e)));raise
if __name__=='__main__':main()
