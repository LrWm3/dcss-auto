"""One fresh clear-only seed at gamma=.9999, evaluated at 500K then 1M."""
import fcntl,json,pathlib,subprocess,sys,time
import torch
import assets
import run_ring_ablations as runner
ROOT=assets.ROOT
SUITE=ROOT/'learning-runs/semantic-clear-only-gamma9999'
def main():
 torch.set_num_threads(1);SUITE.mkdir(exist_ok=True);store=runner.Store(SUITE,2*runner.GIB,10*runner.GIB)
 with (SUITE/'.pipeline.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);start=time.monotonic()
  store.json('status.json',dict(status='building'))
  for clump in [0,1]:
   lib=assets.ASSETS/f'gamma0.9999-clump{clump}.so'
   if not lib.exists():assets.build(clump,.9999)
  original=json.loads((ROOT/'learning-runs/semantic-clear-only-500k/manifest.json').read_text())
  base=dict(original['jobs'][0],id='clear-only-gamma9999-seed0',name='clear-only-gamma9999',gamma=.9999,train_library=str(assets.ASSETS/'gamma0.9999-clump1.so'),eval_library=str(assets.ASSETS/'gamma0.9999-clump0.so'))
  results={};previous=None
  for steps,label in [(500000,'500k'),(1000000,'1m')]:
   stage=SUITE/label;stage.mkdir(exist_ok=True);ss=runner.Store(stage,2*runner.GIB,10*runner.GIB);job=dict(base,steps=steps)
   if previous:
    saved=torch.load(previous/'runs'/job['id']/'latest.pt',map_location='cpu',weights_only=False)
    assert saved['decisions']==500224
    job['source_train_seconds']=saved['train_seconds'];saved['job']=job
    target=pathlib.Path('runs')/job['id']/'latest.pt'
    if not (stage/target).exists():ss.atomic(target,lambda f:torch.save(saved,f),256*runner.MIB)
   m=dict(format='clear-only-gamma9999',corpus=original['corpus'],jobs=[job],sources={str(p.relative_to(runner.ROOT)):runner.digest(p) for sub in ['scripts','src'] for p in sorted((runner.ROOT/sub).iterdir()) if p.suffix in ['.py','.cu','.h']})
   if (stage/'manifest.json').exists():assert json.loads((stage/'manifest.json').read_text())==m
   else:ss.json('manifest.json',m)
   store.json('status.json',dict(status='training',checkpoint=label,started_at=time.time()))
   subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',job['id'],'--output',str(stage),'--max-disk-gb','2','--min-free-gb','10'],check=True)
   result=json.loads((stage/'runs'/job['id']/'result.json').read_text());assert result['decisions']==(500224 if label=='500k' else 1000448)
   results[label]=result
   (ROOT/'results/semantic-clear-only-gamma9999.json').write_text(json.dumps(results,indent=2)+'\n');previous=stage
  store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Both checkpoints complete',flush=True)
if __name__=='__main__':main()
