"""Matched 1M continuations retaining the stronger tactical policy and practice."""
import fcntl,json,pathlib,subprocess,sys,time,torch
ROOT=pathlib.Path(__file__).resolve().parents[2];SCRIPTS=ROOT/'branches/autoregressive-ordinary-v1/scripts';sys.path.insert(0,str(SCRIPTS))
import run_ring_ablations as runner
SUITE=ROOT/'learning-runs/autoregressive-ordinary-retain'
SOURCE=ROOT/'learning-runs/autoregressive-survival-balanced/runs/balanced-seed0/latest.pt'

def main():
 torch.set_num_threads(1);SUITE.mkdir(parents=True,exist_ok=True)
 with (SUITE/'.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);start=time.monotonic();store=runner.Store(SUITE,4*runner.GIB,10*runner.GIB)
  saved=torch.load(SOURCE,map_location='cpu',weights_only=False);assert saved['decisions']==40000512
  template=dict(saved['job'],steps=41000960,evaluation_steps=[41000960],source_train_seconds=saved['train_seconds'],correction_scope='wait',correction_max_awake=2,correction_ordinary_only=True)
  manifest=dict(corpus=json.loads((ROOT/'learning-runs/autoregressive-survival-balanced/manifest.json').read_text())['corpus'],source_checkpoint=str(SOURCE),source_sha256=runner.digest(SOURCE),jobs=[],sources={str(p):runner.digest(p) for p in [pathlib.Path(__file__),*SCRIPTS.glob('*.py')]})
  for name,weight in [('control',0.),('wait',.1)]:
   job=dict(template,id=name+'-seed0',name=name,correction_weight=weight);manifest['jobs'].append(job)
   p=pathlib.Path('runs')/job['id']/'latest.pt'
   if not (SUITE/p).exists():
    c=dict(saved,job=job,history=[],best=None,best_score=(-1.,-1.));store.atomic(p,lambda f:torch.save(c,f),256*runner.MIB)
  if (SUITE/'manifest.json').exists():assert json.loads((SUITE/'manifest.json').read_text())==manifest
  else:store.json('manifest.json',manifest)
  del saved;results={}
  try:
   for i,job in enumerate(manifest['jobs']):
    store.json('status.json',dict(status='training',job=job['id'],queued=[x['id'] for x in manifest['jobs'][i+1:]]));print('Starting',job['id'],flush=True)
    folder=SUITE/'runs'/job['id']
    if not (folder/'result.json').exists():subprocess.run([sys.executable,str(SCRIPTS/'run_ring_ablations.py'),'--worker',job['id'],'--output',str(SUITE),'--max-disk-gb','4','--min-free-gb','10'],check=True)
    r=json.loads((folder/'result.json').read_text());assert r['decisions']==41000960
    results[job['id']]=dict(additional_train_seconds=r['additional_train_seconds'],evaluations=json.loads((folder/'curve.json').read_text()))
    (ROOT/'results/autoregressive-ordinary-retain.json').write_text(json.dumps(dict(source_decisions=40000512,results=results,wall_seconds=time.monotonic()-start),indent=2,allow_nan=False)+'\n')
   store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Retention comparison complete',flush=True)
  except Exception as e:store.json('status.json',dict(status='failed',failure=str(e)));raise
if __name__=='__main__':main()
