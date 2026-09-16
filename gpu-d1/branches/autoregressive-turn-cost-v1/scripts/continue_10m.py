"""Continue the turn-cost 1M checkpoint, preserving optimizer, RNG and live worlds."""
import fcntl,json,pathlib,subprocess,sys,time
import torch
import run_ring_ablations as runner
from assets import ROOT
SOURCE=ROOT/'learning-runs/autoregressive-turn-cost'
SUITE=ROOT/'learning-runs/autoregressive-turn-cost-10m'
def main():
 torch.set_num_threads(1);SUITE.mkdir(parents=True,exist_ok=True)
 store=runner.Store(SUITE,2*runner.GIB,10*runner.GIB);start=time.monotonic()
 with (SUITE/'.pipeline.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  old=json.loads((SOURCE/'manifest.json').read_text());m=dict(format='autoregressive-turn-cost-10m',corpus=old['corpus'],jobs=[],continuations={},sources={str(p.relative_to(runner.ROOT)):runner.digest(p) for sub in ['scripts','src'] for p in sorted((runner.ROOT/sub).iterdir()) if p.suffix in ['.py','.cu','.h']})
  for original_job in old['jobs']:
   cp=SOURCE/'runs'/original_job['id']/'latest.pt';saved=torch.load(cp,map_location='cpu',weights_only=False)
   assert saved['job']==original_job and saved['decisions']==1000448
   job=dict(original_job,steps=10000000,evaluation_steps=[5000000,10000000],source_train_seconds=saved['train_seconds'])
   m['jobs'].append(job);m['continuations'][job['id']]=dict(checkpoint=str(cp),sha256=runner.digest(cp),decisions=saved['decisions'],train_seconds=saved['train_seconds'])
   dest=pathlib.Path('runs')/job['id']/'latest.pt'
   if not (SUITE/dest).exists():
    # Retag only the stopping budget and timing metadata. Preserve all training state.
    saved['job']=job;store.atomic(dest,lambda f:torch.save(saved,f),256*runner.MIB)
  if (SUITE/'manifest.json').exists():assert json.loads((SUITE/'manifest.json').read_text())==m,'Continuation plan/source drift'
  else:store.json('manifest.json',m)
  for job in m['jobs']:
   if (SUITE/'runs'/job['id']/'result.json').exists():continue
   store.json('status.json',dict(status='training',job=job['id'],started_at=time.time()));print('Continuing',job['id'],flush=True)
   subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',job['id'],'--output',str(SUITE),'--max-disk-gb','2','--min-free-gb','10'],check=True)
  results={j['id']:json.loads((SUITE/'runs'/j['id']/'result.json').read_text()) for j in m['jobs']}
  assert all(r['decisions']==10000384 for r in results.values())
  (ROOT/'results/autoregressive-turn-cost-10m.json').write_text(json.dumps(results,indent=2)+'\n')
  store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Turn-cost continuation complete',flush=True)
if __name__=='__main__':main()
