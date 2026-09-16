"""Continue the seen-floor / +3 clear / -4 death seed-0 run to 30M."""
import fcntl
import json
import pathlib
import shutil
import subprocess
import sys
import time
import torch
import run_ring_ablations as runner


def equal(a,b):
 if isinstance(a,torch.Tensor):return torch.equal(a,b)
 if isinstance(a,dict):return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
 if isinstance(a,(tuple,list)):return type(a)==type(b) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
 return a==b


def main():
 started=time.monotonic();root=runner.ROOT.parents[1]
 source_suite=root/'learning-runs/vision15-seen-death4-10m'
 suite=root/'learning-runs/vision15-seen-death4-30m'
 job_id='tiles_seen_death4-seed0';source=source_suite/'runs'/job_id/'latest.pt'
 old_manifest=json.loads((source_suite/'manifest.json').read_text());old_job=old_manifest['jobs'][0]
 assert runner.corpus_manifest(pathlib.Path(old_manifest['corpus']))==old_manifest['maps']
 sources={name:runner.digest(runner.ROOT/name) for name in runner.SOURCE_FILES}
 sources['scripts/run_continue.py']=runner.digest(pathlib.Path(__file__))
 for name in runner.SOURCE_FILES:
  if name!='scripts/run_ring_ablations.py':assert sources[name]==old_manifest['sources'][name],name
 job=dict(old_job,steps=30_000_000)
 assert old_job['steps']==10_000_000 and old_job['seed']==0
 assert {k:v for k,v in job.items() if k!='steps'}=={k:v for k,v in old_job.items() if k!='steps'}
 suite.mkdir(parents=True,exist_ok=True);store=runner.Store(suite,2*runner.GIB,5*runner.GIB)
 source_hash=runner.digest(source)
 with (suite/'.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if not (suite/'manifest.json').exists():
   assert not any(p.name!='.lock' for p in suite.iterdir()),'Fresh output required after incomplete preparation'
   old=torch.load(source,weights_only=False,map_location='cpu')
   assert old['job']==old_job and old['decisions']==10_027_008
   saved=dict(old,job=job)
   checkpoint=pathlib.Path('runs')/job_id/'latest.pt'
   store.atomic(checkpoint,lambda f:torch.save(saved,f),128*runner.MIB)
   check=torch.load(suite/checkpoint,weights_only=False,map_location='cpu')
   assert check['job']==job
   for key in old:
    if key!='job':assert equal(old[key],check[key]),key
   for name in ['best.pt']:
    shutil.copy2(source_suite/'runs'/job_id/name,suite/'runs'/job_id/name)
   key=runner.library_key(job);(suite/'build').mkdir()
   for suffix in ['.so','.sha256']:shutil.copy2(source_suite/'build'/(key+suffix),suite/'build'/(key+suffix))
   assert runner.digest(suite/'build'/(key+'.so'))==(suite/'build'/(key+'.sha256')).read_text().strip()
   store.json('continuation.json',dict(source_checkpoint_sha256=source_hash,source_decisions=old['decisions'],source_train_seconds=old['train_seconds'],state_transfer_exact=True,preserved='model, optimizer, live worlds, observations, masks, CPU/CUDA RNG, work totals, history, best selection and counters',only_checkpoint_change='job.steps: 10000000 -> 30000000'))
   store.json('manifest.json',dict(old_manifest,jobs=[job],sources=sources))
   del saved,old,check
  manifest=json.loads((suite/'manifest.json').read_text());assert manifest['sources']==sources and manifest['jobs']==[job]
  if not (suite/'runs'/job_id/'result.json').exists():
   subprocess.run([sys.executable,str(runner.ROOT/'scripts/run_ring_ablations.py'),'--worker',job_id,'--output',str(suite)],check=True)
 assert runner.digest(source)==source_hash
 curve=json.loads((suite/'runs'/job_id/'curve.json').read_text())
 previous=json.loads((source_suite/'runs'/job_id/'curve.json').read_text())
 assert curve[:len(previous)]==previous
 rows=[r for r in curve if r['decisions']>=10_027_008]
 assert [r['decisions'] for r in rows]==[10_027_008,15_007_744,20_021_248,25_001_984,30_015_488]
 report=dict(seed=0,manifest=manifest,continuation=json.loads((suite/'continuation.json').read_text()),wall_seconds=time.monotonic()-started,checkpoints=[])
 for row in rows:
  folder=source_suite if row['decisions']==10_027_008 else suite
  snapshot=folder/'runs'/job_id/'snapshots'/f"{row['decisions']:012d}.pt"
  r=dict(row,checkpoint_sha256=runner.digest(snapshot),additional_train_seconds=row['train_seconds']-report['continuation']['source_train_seconds'])
  report['checkpoints'].append(r)
  print(json.dumps(dict(decisions=r['decisions'],train_seconds=r['train_seconds'],**{k:r['sampled'][k] for k in ['clear_rate','death_rate','timeout_rate','turns','kills']})),flush=True)
 (root/'results/vision15-seen-death4-30m.json').write_text(json.dumps(report,separators=(',',':'))+'\n')

if __name__=='__main__':main()
