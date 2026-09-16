"""Plan paired continuations and separate fresh architecture screens."""
import json
import pathlib
import torch
import run_ring_ablations as runner
from assets import ROOT,ASSETS
SUITE=ROOT/'learning-runs/vision15-tactical-next'

def source(seed,placement):
    if seed==0:
        if placement=='ordinary':return ROOT/'learning-runs/vision15-seen-death4-30m','tiles_seen_death4-seed0'
        return ROOT/'learning-runs/vision15-clumps-30m','clumps_third-seed0'
    return ROOT/'learning-runs/vision15-direction-seeds-30m',f'{"ordinary" if placement=="ordinary" else "clumps_third"}-seed{seed}'

def library(suite,job):
    candidates=list((suite/'build').glob('*.so'))
    if len(candidates)==1:return candidates[0]
    return next(p for p in candidates if f'-clump{job["clump_mode"]}-' in p.name)

def plan():
    jobs=[];reference=json.loads((ROOT/'learning-runs/vision15-clumps-30m/manifest.json').read_text())
    eval_lib=library(ROOT/'learning-runs/vision15-clumps-30m',{'clump_mode':0})
    for kind in ['continue','targeted','enemy_set','d4_exact']:
        for seed in [0,1,2]:
            for placement in ['ordinary','clumped']:
                suite,name=source(seed,placement);m=json.loads((suite/'manifest.json').read_text());old=next(j for j in m['jobs'] if j['id']==name)
                job=dict(old,name=f'{kind}_{placement}',id=f'{kind}_{placement}-seed{seed}',steps=100000000 if kind in ['continue','targeted'] else 30000000,
                         seed=seed,architecture=kind if kind in ['enemy_set','d4_exact'] else 'mlp',curriculum=kind=='targeted',
                         train_library=str(library(suite,old)),eval_library=str(eval_lib),tactical_library=str(ASSETS/'tactical.so'),tactical_corpus=str(ASSETS/'train'),
                         checkpoint_every=10000000,source_suite=str(suite),source_job=name)
                if kind in ['continue','targeted']:
                    oldresult=json.loads((suite/'runs'/name/'result.json').read_text())
                    job.update(source_train_seconds=oldresult['train_seconds'],source_decisions=oldresult['decisions'])
                jobs.append(job)
    return dict(format='tactical-next-v1',frozen_bank_sha256=runner.digest(ASSETS/'frozen.pt'),tactical_library_sha256=runner.digest(ASSETS/'tactical.so'),corpus=reference['corpus'],maps=reference['maps'],jobs=jobs,
        sources={str(p.relative_to(runner.ROOT)):runner.digest(p) for sub in ['scripts','src'] for p in sorted((runner.ROOT/sub).iterdir()) if p.suffix in ['.py','.cu','.h']},geometry=json.loads((ASSETS/'geometry-checks.json').read_text()))

def same(a,b):
    if isinstance(a,torch.Tensor):return torch.equal(a,b)
    if isinstance(a,dict):return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
    if isinstance(a,(tuple,list)):return type(a)==type(b) and len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    return a==b

def initialize(store,job):
    folder=pathlib.Path('runs')/job['id'];latest=store.root/folder/'latest.pt'
    if 'source_decisions' not in job or latest.exists():return
    sourcefile=pathlib.Path(job['source_suite'])/'runs'/job['source_job']/'latest.pt'
    saved=torch.load(sourcefile,map_location='cpu',weights_only=False)
    assert saved['decisions']==30015488
    oldjob=saved['job'];saved['job']=job
    store.atomic(folder/'latest.pt',lambda f:torch.save(saved,f),256*runner.MIB)
    check=torch.load(latest,map_location='cpu',weights_only=False)
    assert same(saved,check)
    store.json(folder/'continuation.json',dict(source_checkpoint_sha256=runner.digest(sourcefile),state_optimizer_rng_exact=True,only_initial_checkpoint_change='job metadata; all live worlds/optimizer/model/RNG/counters/history preserved',source_job=oldjob))
    compact=dict(job=job,decisions=saved['decisions'],train_seconds=saved['train_seconds'],model=saved['model'])
    store.atomic(folder/'snapshots'/f'{saved["decisions"]:012d}.pt',lambda f:torch.save(compact,f),16*runner.MIB)
    print('Prepared exact continuation',job['id'],flush=True)

if __name__=='__main__':print(json.dumps(plan(),indent=2))
