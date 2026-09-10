"""Exhaustive six-option diagnostic on two inspected held-out RNG families.

Not training data or a new unbiased benchmark. No controller/model changes.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import shutil
from augmentation_dataset import read, verify_result, classify
from augment_encounters import POLICIES
from bench import HERE, ENGINE, sha
from character_dataset import canonical
from evaluate_rng_holdout import pack
from rich_features import features
from rich_goals import run
from train_encounters import write

TARGETS = ('fresh-evaluation/collection/encounter-015',
           'fresh-evaluation/supplemental/encounter-034')


def trial(task):
    family, variant, initial, root = task
    work=Path(root)/family['id']/f"rng-{variant['offset']:02d}"
    work.mkdir(parents=True,exist_ok=False)
    result=dict(family_id=family['id'], seed=family['seed'], split=family['split'],
                offset=variant['offset'],rows=[],status='failed')
    try:
        if shutil.disk_usage(work).free<8*1024**3: raise RuntimeError('Disk safety floor')
        case=Path(variant['case']); meta=read(case/'case.json')
        for name,key in [('checkpoint.cs','save_sha256'),('trial.rc','rc_sha256')]:
            if sha(case/name)!=meta[key]: raise ValueError('Verified checkpoint changed')
        if meta['engine_sha256']!=sha(ENGINE): raise ValueError('Engine mismatch')
        if meta['augmentation']!=dict(hp_percent=100,rng_draws=variant['offset']):
            raise ValueError('RNG recipe mismatch')
        old={r['option']:r for r in variant['rows']}
        for option in POLICIES:
            r=verify_result(run(dict(id=family['id']+f"/rng-{variant['offset']:02d}",seed=family['seed']),
                                case,work/option.replace(':','-'),option,600))
            r.update(split=family['split'],split_group=family['seed'])
            if 'features' in r and r['features']!=features(initial): raise ValueError('Initial features changed')
            if r.get('trace'):
                with Path(r['trace']).open() as stream:
                    first=json.loads(next(stream))['observation']
                if canonical(first)!=canonical(initial): raise ValueError('Initial gameplay state changed')
            previous=old.get(option)
            r['prior_outcome_match']=None
            if previous and previous.get('evidence_verified') and r.get('evidence_verified'):
                r['prior_outcome_match']=r['outcome']==previous['outcome']
                if not r['prior_outcome_match']: raise ValueError('Previously tested option diverged')
            r['archive']=pack(r['worker']); result['rows'].append(r)
            write(work/'progress.json',result)
        result['status']='complete'
    except Exception as exc: result['error']=repr(exc)
    result['label']=classify(result['rows']);write(work/'result.json',result)
    print(dict(family=family['id'],offset=variant['offset'],status=result['status'],error=result.get('error'),
               outcomes={r['option']:r['outcome'] for r in result['rows']}),flush=True)
    return result


def summary(rows):
    out={}
    for ident in TARGETS:
        fs=[f for f in rows if f['family_id']==ident]
        complete=[f for f in fs if f['status']=='complete' and f['label']['complete']]
        out[ident]=dict(offsets=len(fs),complete_matrices=len(complete),
            strategies={o:dict(Counter(r['outcome'] for f in fs for r in f['rows'] if r['option']==o))
                        for o in POLICIES},
            any_strategy_wins=sum(bool(f['label']['successful']) for f in complete),
            all_available_strategies_die=[f['offset'] for f in complete if not f['label']['successful']],
            matrices=[dict(offset=f['offset'],**f['label']) for f in fs])
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();source=a.source.resolve();root=a.output.resolve()
    manifest=read(source/'manifest.json')
    for name,digest in manifest['frozen'].items():
        if sha(Path(name))!=digest: raise ValueError('Frozen sweep input changed: '+name)
    completed=read(source/'completion.json')
    if sha(source/'summary.json')!=completed['summary_sha256']: raise ValueError('Sweep summary changed')
    families={f['id']:f for f in read(source/'coverage.json')}
    baseline={f['id']:f for f in read(Path(manifest['baseline_offset_zero'])/'coverage.json')}
    tasks=[];archives=[]
    for ident in TARGETS:
        f=families[ident]
        if f['split'] not in ('validation','test','evaluation_only'): raise ValueError('Not held out')
        if {v['offset'] for v in f['variants']}!=set(range(1,11)): raise ValueError('Missing offsets')
        for v in f['variants']:
            if not v['verified']: raise ValueError('Unverified source variant')
            archives+=v['archives']+[r['archive'] for r in v['rows']]
            tasks.append((f,v,baseline[ident]['initial'],str(root)))
    for archive in archives:
        if sha(Path(archive['path']))!=archive['sha256']: raise ValueError('Source evidence changed')
    frozen=dict(manifest['frozen'])
    for path in (source/'coverage.json',source/'manifest.json',Path(__file__),HERE/'evaluate_rng_holdout.py'):
        frozen[str(path.resolve())]=sha(path)
    root.mkdir(parents=True,exist_ok=False)
    write(root/'manifest.json',dict(frozen=frozen,targets=TARGETS,policies=POLICIES,offsets=list(range(1,11)),
                                  fitting=False,production_export=False,purpose='Inspected held-out diagnostic'))
    write(root/'status.json',dict(status='running',finished=0,matrices=20,trials=120))
    results=[]
    with ProcessPoolExecutor(max_workers=6) as pool:
        for future in as_completed([pool.submit(trial,t) for t in tasks]):
            results.append(future.result());write(root/'coverage.json',results)
            write(root/'status.json',dict(status='running',finished=len(results),matrices=20,trials=120))
    for path,digest in frozen.items():
        if sha(Path(path))!=digest: raise ValueError('Frozen file changed: '+path)
    for f in results:
        for r in f['rows']:
            if sha(Path(r['archive']['path']))!=r['archive']['sha256']: raise ValueError('Archive changed')
    write(root/'summary.json',summary(results))
    write(root/'completion.json',dict(summary_sha256=sha(root/'summary.json'),
        complete_matrices=sum(f['status']=='complete' and f['label']['complete'] for f in results),
        trials=sum(len(f['rows']) for f in results),fitting=False,production_export=False))
    write(root/'status.json',dict(status='complete',finished=len(results)))


if __name__=='__main__':main()
