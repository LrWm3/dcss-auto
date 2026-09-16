"""Nine paired 30M continuations from the three D4/clumped 30M checkpoints."""
import json,pathlib,torch
import run_ring_ablations as runner
from assets import ROOT,ASSETS
SUITE=ROOT/'learning-runs/vision15-choice-practice'
SOURCE=ROOT/'learning-runs/vision15-tactical-next'

def plan():
 old=json.loads((SOURCE/'manifest.json').read_text());jobs=[]
 for seed in range(3):
  original=next(j for j in old['jobs'] if j['id']==f'd4_exact_clumped-seed{seed}')
  result=json.loads((SOURCE/'runs'/original['id']/'result.json').read_text())
  for task in ['baseline','target','sleep']:
   jobs.append(dict(original,name=task,id=f'{task}-seed{seed}',steps=60000000,source_suite=str(SOURCE),source_job=original['id'],source_decisions=result['decisions'],source_train_seconds=result['train_seconds'],curriculum=task!='baseline',tactical_maps=16,tactical_library=str(ASSETS/'tactical.so'),tactical_corpus=str(ASSETS/task/'train')))
 return dict(format='choice-practice-v1',native_sources={str(p.relative_to(ROOT)):runner.digest(p) for p in [ROOT/'branches/vision15-tactical-next-v1/src/learn.cu',ROOT/'branches/vision15-tactical-next-v1/src/sim.h']},jobs=jobs,corpus=old['corpus'],maps=old['maps'],geometry=json.loads((ASSETS/'geometry-checks.json').read_text()),tactical_library_sha256=runner.digest(ASSETS/'tactical.so'),sources={str(p.relative_to(runner.ROOT)):runner.digest(p) for sub in ['scripts','src'] for p in sorted((runner.ROOT/sub).iterdir()) if p.suffix in ['.py','.cu','.h']})

def same(a,b):
 if isinstance(a,torch.Tensor):return torch.equal(a,b)
 if isinstance(a,dict):return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
 if isinstance(a,(tuple,list)):return type(a)==type(b) and len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
 return a==b

def initialize(store,job):
 folder=pathlib.Path('runs')/job['id'];latest=store.root/folder/'latest.pt'
 if latest.exists():return
 source=pathlib.Path(job['source_suite'])/'runs'/job['source_job']/'latest.pt';saved=torch.load(source,map_location='cpu',weights_only=False)
 assert saved['decisions']==job['source_decisions']==30015488
 saved['job']=job;store.atomic(folder/'latest.pt',lambda f:torch.save(saved,f),256*runner.MIB)
 assert same(saved,torch.load(latest,map_location='cpu',weights_only=False))
 store.json(folder/'continuation.json',dict(source_sha256=runner.digest(source),state_optimizer_rng_exact=True))
 compact=dict(job=job,decisions=saved['decisions'],train_seconds=saved['train_seconds'],model=saved['model'])
 store.atomic(folder/'snapshots'/f'{saved["decisions"]:012d}.pt',lambda f:torch.save(compact,f),16*runner.MIB)
 print('Prepared exact continuation',job['id'],flush=True)
