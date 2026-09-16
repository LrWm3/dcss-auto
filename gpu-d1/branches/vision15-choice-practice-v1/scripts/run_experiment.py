"""Sequential, restartable queue for target-selection and sleep/recovery curricula."""
import fcntl,json,pathlib,subprocess,sys,time
from prepare import SUITE,SOURCE,plan,initialize
from assets import ROOT
import run_ring_ablations as runner

def main():
 SUITE.mkdir(parents=True,exist_ok=True);store=runner.Store(SUITE,3*runner.GIB,10*runner.GIB);start=time.monotonic()
 with (SUITE/'.pipeline.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  manifest=plan();path=SUITE/'manifest.json'
  if path.exists():assert json.loads(path.read_text())==manifest,'Source/plan drift'
  else:store.json('manifest.json',manifest)
  def run(script,*args):subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name(script)),*map(str,args)],check=True)
  for seed in range(3):
   out=ROOT/'results'/f'choice-practice-source-seed{seed}.json'
   if not out.exists():run('evaluate.py','--checkpoint',SOURCE/'runs'/f'd4_exact_clumped-seed{seed}'/'snapshots/000030015488.pt','--output',out)
  for job in manifest['jobs']:
   directory=SUITE/'runs'/job['id']
   if not (directory/'result.json').exists():
    initialize(store,job);store.json('status.json',dict(status='training',job=job['id'],started_at=time.time()));print('Starting',job['id'],flush=True)
    run('run_ring_ablations.py','--worker',job['id'],'--output',SUITE,'--max-disk-gb',3,'--min-free-gb',10)
   for milestone in [40,50,60]:
    n=((milestone*1000000+32767)//32768)*32768;checkpoint=directory/'snapshots'/f'{n:012d}.pt';out=ROOT/'results'/f'choice-practice-{job["id"]}-{milestone}m.json'
    if not out.exists():
     store.json('status.json',dict(status='evaluation',job=job['id'],milestone=milestone));run('evaluate.py','--checkpoint',checkpoint,'--output',out)
   # Regression: old frozen combat states and held-out hallway/pocket worlds.
   output=ROOT/'results'/f'choice-practice-{job["id"]}-regression.json'
   if not output.exists():
    subprocess.run([sys.executable,str(ROOT/'branches/vision15-tactical-next-v1/scripts/evaluate_extra.py'),str(checkpoint),str(output)],check=True)
  results=[json.loads((SUITE/'runs'/j['id']/'result.json').read_text()) for j in manifest['jobs']]
  (ROOT/'results/choice-practice-training-summary.json').write_text(json.dumps(dict(jobs=results,wall_seconds=time.monotonic()-start),separators=(',',':'))+'\n')
  store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Choice-practice queue complete',flush=True)
if __name__=='__main__':main()
