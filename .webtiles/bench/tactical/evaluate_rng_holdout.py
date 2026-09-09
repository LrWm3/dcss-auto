"""Ten fixed RNG offsets of every held-out encounter; frozen model, no fitting."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
from augmentation_dataset import read, verify_result
from augment_encounters import make_variant, startup
from bench import HERE, ENGINE, sha
from character_dataset import canonical
from goal_env import GoalEnvironment
from goal_controllers import Controller
from rich_features import features
from rich_goals import run, select
from train_encounters import write

NAMES = ('candidate','pursue_no_berserk','pursue_berserk')


def pack(worker):
    """Archive only this run's closed worker; verify every byte before removal."""
    worker = Path(worker)
    if not worker.name.startswith('worker-') or not (worker/'run.json').is_file():
        raise ValueError('Not a private worker')
    files = {str(p.relative_to(worker)):sha(p) for p in worker.rglob('*') if p.is_file()}
    if any(p.is_symlink() for p in worker.rglob('*')): raise ValueError('Unexpected symlink')
    archive = worker.with_suffix('.tar.gz')
    with tarfile.open(archive,'x:gz',compresslevel=1) as tar:
        tar.add(worker,arcname=worker.name)
    checked = {}
    with tarfile.open(archive,'r:gz') as tar:
        for member in tar:
            if member.isfile():
                stream = tar.extractfile(member)
                digest = hashlib.sha256()
                for block in iter(lambda:stream.read(1024*1024),b''): digest.update(block)
                checked[str(Path(member.name).relative_to(worker.name))] = digest.hexdigest()
    if checked != files: raise ValueError('Archive verification failed')
    result = dict(path=str(archive),sha256=sha(archive),files=files,original_worker=str(worker))
    shutil.rmtree(worker)  # Exact new private directory; full verified archive retained.
    return result


def replay(case, root, initial, reference=None):
    env = GoalEnvironment(root)
    try:
        state,errors = startup(env,case)
        if canonical(state) != canonical(initial): raise ValueError('RNG recipe changed visible initial state')
        states = [state]; controller = Controller('pursue',False)
        for i in range(12):
            if state.get('terminal'): break
            action = reference[i]['action'] if reference is not None else controller(state)
            state = env.step(action); states.append(state)
            if reference is not None and canonical(state)!=canonical(reference[i]['next_observation']):
                raise ValueError('Neutral engine differs from original replay')
        return states, str(env.work), errors
    finally: env.close()


def rates(variants, planned=10):
    report = {}
    for name in NAMES:
        rs = [r for v in variants for r in v['rows'] if r['evaluator']==name]
        wins = sum(r['outcome']=='recovered_quiet' and r.get('evidence_verified',False) for r in rs)
        deaths = sum(r['outcome']=='death' and r.get('evidence_verified',False) for r in rs)
        unknown = planned-wins-deaths
        report[name] = dict(wins=wins,deaths=deaths,unknown=unknown,total=planned,
            recovery_rate_lower=wins/planned,recovery_rate_upper=(wins+unknown)/planned,
            outcomes=dict(Counter(r['outcome'] for r in rs)))
    return report


def family(task):
    original, source, root, model = task
    work = Path(root)/original['id']; work.mkdir(parents=True,exist_ok=False)
    f = dict(id=original['id'],seed=original['seed'],split=original['split'],variants=[],status='failed')
    try:
        parent = Path(source)/original['id']/'rich-case'
        initial = original['initial']
        if initial['hp']!=initial['max_hp']: raise ValueError('RNG-only recipe requires exact HP preservation')
        neutral = work/'neutral-case'
        make_variant(parent,neutral,dict(hp_percent=100,rng_draws=0),f['id'])
        old = next(r for r in original['rows'] if r['evaluator']=='pursue_no_berserk')
        if sha(Path(old['trace']))!=old['trace_sha256']: raise ValueError('Original trace changed')
        with Path(old['trace']).open() as stream:
            reference = [json.loads(next(stream)) for _ in range(12)]
        _,worker,errors = replay(neutral,work/'neutral',initial,reference)
        f['neutral'] = dict(passed=True,archive=pack(worker),startup_errors=errors)
        for offset in range(1,11):
            vr = work/f'rng-{offset:02d}'; vr.mkdir()
            v = dict(offset=offset,rows=[],verified=False,archives=[])
            try:
                if shutil.disk_usage(work).free<8*1024**3: raise RuntimeError('Disk safety floor')
                case = vr/'case'; make_variant(parent,case,dict(hp_percent=100,rng_draws=offset),f['id'])
                a,wa,ea = replay(case,vr/'verify',initial)
                v['archives'].append(pack(wa))
                b,wb,eb = replay(case,vr/'verify',initial)
                v['archives'].append(pack(wb))
                if [canonical(s) for s in a]!=[canonical(s) for s in b]: raise ValueError('Repeated RNG replay mismatch')
                v.update(verified=True,startup_errors=ea+eb,case=str(case))
                for name,option in zip(NAMES,('selector','pursue:0','pursue:1')):
                    r = verify_result(run(dict(id=f['id']+f'/rng-{offset:02d}',seed=f['seed']),case,vr/name,
                                          option,600,model if name=='candidate' else None))
                    r.update(evaluator=name,offset=offset,split=f['split'],split_group=f['seed'])
                    if 'features' in r and r['features']!=features(initial): raise ValueError('Initial feature mismatch')
                    if name=='candidate' and r['option']!=select(model,initial): raise ValueError('RNG influenced model choice')
                    r['archive']=pack(r['worker']); v['rows'].append(r)
                    write(vr/'result.json',v)
            except Exception as exc: v['error']=repr(exc)
            f['variants'].append(v); write(work/'progress.json',f)
            print(dict(id=f['id'],offset=offset,verified=v['verified'],error=v.get('error'),
                       outcomes={r['evaluator']:r['outcome'] for r in v['rows']}),flush=True)
        f['status']='complete'
    except Exception as exc: f['error']=repr(exc)
    f['rates']=rates(f['variants']); write(work/'family.json',f)
    return f


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path); p.add_argument('model',type=Path); p.add_argument('output',type=Path)
    a=p.parse_args(); source=a.source.resolve(); root=a.output.resolve()
    if ENGINE.name!='crawl-tactical-augment' or os.environ.get('DCSS_TACTICAL_AUGMENT')!='1':
        raise ValueError('Explicit augmentation lab engine required')
    original_manifest=read(source/'manifest.json')
    for name,digest in original_manifest['frozen'].items():
        if sha(Path(name))!=digest: raise ValueError('Held-out source changed: '+name)
    if sha(a.model)!=read(source/'completion.json')['model_sha256']: raise ValueError('Model changed')
    families=read(source/'coverage.json'); trained=set(read(a.model.parent/'manifest.json')['training_seeds'])
    if any(f['seed'] in trained or f['split']=='train' or not f.get('prefix_verified') for f in families):
        raise ValueError('Invalid held-out source')
    root.mkdir(parents=True,exist_ok=False)
    paths=[source/'coverage.json',source/'manifest.json',a.model,ENGINE,Path(__file__)]
    paths += [Path(name) for name in original_manifest['frozen']]
    paths += [HERE/'augment_encounters.py']
    frozen={str(path.resolve()):sha(path) for path in paths}
    write(root/'manifest.json',dict(frozen=frozen,offsets=list(range(1,11)),families=len(families),
        baseline_offset_zero=str(source),fitting=False,production_export=False,
        note='Consecutive RNG stream offsets are correlated, not independent seeds. Visible initial states unchanged.'))
    write(root/'status.json',dict(status='running',finished=0,encounters=len(families),variants=len(families)*10))
    results=[]
    with ProcessPoolExecutor(max_workers=6) as pool:
        for future in as_completed([pool.submit(family,(f,str(source),str(root),read(a.model))) for f in families]):
            results.append(future.result()); write(root/'coverage.json',results)
            write(root/'status.json',dict(status='running',finished=len(results),encounters=len(families)))
    for name,digest in frozen.items():
        if sha(Path(name))!=digest: raise ValueError('Frozen input changed: '+name)
    archives=[]
    for f in results:
        if f.get('neutral'): archives.append(f['neutral']['archive'])
        for v in f['variants']:
            archives+=v['archives']; archives += [r['archive'] for r in v['rows']]
    for archive in archives:
        if sha(Path(archive['path']))!=archive['sha256']: raise ValueError('Evidence archive changed')
    variants=[v for f in results for v in f['variants']]
    summary=dict(encounters=len(results),verified_variants=sum(v['verified'] for v in variants),
        family_status=dict(Counter(f['status'] for f in results)),
        trials=sum(len(v['rows']) for v in variants),rates=rates(variants,len(families)*10),
        encounter_rates=[dict(id=f['id'],seed=f['seed'],split=f['split'],rates=f['rates']) for f in results],
        archives_verified=len(archives),fitting=False,production_export=False)
    write(root/'summary.json',summary)
    write(root/'completion.json',dict(model_sha256=sha(a.model),summary_sha256=sha(root/'summary.json'),
        archives_verified=len(archives),fitting=False,production_export=False))
    write(root/'status.json',dict(status='complete',finished=len(results)))


if __name__=='__main__': main()
