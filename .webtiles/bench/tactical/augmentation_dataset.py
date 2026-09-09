"""Generate, replay-check, label and split synthetic encounters. Never fits a model.

Paths in config are relative to the repository. Resume requires identical inputs,
engines and controller sources. Each seed and all its derivatives keep one split.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from bench import HERE, ROOT, ENGINE, sha
from dataset_splits import partition_map
from goal_env import derive, GoalEnvironment
from goal_controllers import Recovery, clean
from augment_encounters import (POLICIES, make_variant, validate_recipe, rollout,
                                verify_variant, neutral_check)
from run_goals import SOURCES, run
from train_encounters import write
from verify_resume import normalized
from startup_retry import retryable, run_with_retry


def read(path): return json.loads(Path(path).read_text())


def inventory(cfg):
    splits=partition_map(read(ROOT/cfg['partitions']))
    reserved=read(ROOT/cfg['reservation'])['evaluation_only']
    if set(reserved) & set(splits): raise ValueError('Reserved seed overlaps development')
    splits.update({s:'evaluation_only' for s in reserved})
    entries=[];seen=set()
    for source in cfg['datasets']:
        for e in read(ROOT/source['index'])['cases']:
            e=dict(e,id=source['name']+'/'+e['id'],dataset=source['name'])
            if e['id'] in seen: raise ValueError('Duplicate encounter ID')
            seen.add(e['id'])
            if e.get('split_group')!=e['seed']: raise ValueError('Seed group mismatch')
            e['split']=splits.get(e['seed'],'unassigned')
            e['family_id']=e['id']
            entries.append(e)
    return entries


def classify(rows):
    """Only complete audited win/death comparisons qualify; errors aren't losses."""
    by={r['option']:r for r in rows}
    if len(by)!=len(rows) or set(by)!=set(POLICIES):
        return dict(complete=False,mixed=False,reason='missing or duplicate policy')
    wins=sorted(o for o,r in by.items() if r['outcome']=='recovered_quiet')
    losses=sorted(o for o,r in by.items() if r['outcome']=='death')
    masked=sorted(o for o,r in by.items() if r['outcome']=='masked')
    unknown=sorted(o for o,r in by.items() if r['outcome'] not in
                   ('recovered_quiet','death','masked') or
                   not r.get('evidence_verified'))
    return dict(complete=not unknown,mixed=bool(wins and losses and not unknown),
                successful=wins,failing=losses,unavailable=masked,unknown=unknown)


def verify_result(r):
    """Verify success endpoint/death transition; retain trace hashes for training."""
    r=dict(r)
    if r['outcome']=='masked':
        r['evidence_verified']=r['option'] not in r.get('available',[])
        return r
    path=Path(r['worker'])/'transitions.jsonl'
    if not path.exists(): return dict(r,evidence_verified=False)
    recovery=Recovery();last=None
    with path.open() as f:
        for line in f:
            t=json.loads(line)
            recovery.observe(t['observation'],t['next_observation']);last=t
    valid=False
    if r['outcome']=='recovered_quiet':
        valid=bool(last and clean(last['next_observation']) and recovery.quiet>=20)
    elif r['outcome']=='death':
        valid=bool(last and last['terminated'] and
                   last['next_observation'].get('terminal')=='death')
        terminal=last['next_observation'] if last else {}
        if terminal.get('evidence'):
            valid=valid and sha(Path(terminal['evidence']))==terminal['evidence_sha256']
    return dict(r,evidence_verified=valid,trace=str(path),trace_sha256=sha(path))


def reference(case,root,steps):
    env=GoalEnvironment(root)
    try:
        states,errors=rollout(env,case,steps)
        write(root/'reference.json',dict(worker=str(env.work),initial=states[0],
              startup_errors=errors,trace=str(env.work/'transitions.jsonl')))
    finally: env.close()


def compatible_cache(old,new):
    """Only orchestration/comparison may differ, never gameplay or input data."""
    for key in ('config','entries','inputs','engine_sha256','parent_engine_sha256'):
        if old[key]!=new[key]: raise ValueError('Reuse mismatch: '+key)
    for name in SOURCES+('augment_encounters.py',):
        if old['sources'][name]!=new['sources'][name]:
            raise ValueError('Reuse gameplay source changed: '+name)


def reuse_families(origin,root,manifest):
    old=read(origin/'manifest.json');compatible_cache(old,manifest);reused=[]
    for e in manifest['entries']:
        path=origin/e['id']/'family.json'
        if not path.exists(): continue
        f=read(path)
        if f['status']!='generated' or len(f['variants'])!=len(manifest['config']['recipes']): continue
        if (f['id'],f['seed'],f['split'])!=(e['id'],e['seed'],e['split']):
            raise ValueError('Cached family identity changed')
        for v,recipe in zip(f['variants'],manifest['config']['recipes']):
            if not v['replay_verified'] or v['recipe']!=recipe:
                raise ValueError('Cached variant not verified')
            traces=[]
            for worker,digest in zip(v['workers'],v['trace_sha256']):
                trace=Path(worker)/'transitions.jsonl'
                if sha(trace)!=digest: raise ValueError('Verification trace changed')
                records=[json.loads(line) for line in trace.read_text().splitlines()]
                traces.append([normalized(records[0]['observation'])]+
                              [normalized(t['next_observation']) for t in records])
            if len(traces)!=2 or traces[0]!=traces[1]: raise ValueError('Cached replay mismatch')
            for row in v['rows']:
                if row.get('trace') and sha(Path(row['trace']))!=row['trace_sha256']:
                    raise ValueError('Cached trial trace changed')
            if len(v['rows'])!=len(POLICIES): raise ValueError('Incomplete cached policies')
        n=f['neutral']
        if (not n['passed'] or sha(Path(n['reference']))!=n['reference_sha256'] or
            sha(Path(n['worker'])/'transitions.jsonl')!=n['trace_sha256']):
            raise ValueError('Neutral evidence changed')
        f['reused_from']=dict(path=str(path),sha256=sha(path),
                             manifest_sha256=sha(origin/'manifest.json'))
        (root/e['id']).mkdir(parents=True,exist_ok=False)
        write(root/e['id']/'family.json',f);reused.append(e['id'])
    write(root/'reuse.json',dict(origin=str(origin),families=reused,
        policy='Same inputs/gameplay sources; rechecked prefix traces; terminal provenance ignored'))
    return reused


def policy_trial(entry,case,root,policy,steps,previous=None):
    # Each physical attempt owns new files; a completed gameplay result is never
    # rerolled. Preserve an interrupted retry directory on a later resume.
    def attempt(index):
        target=root/f'attempt-{index}'
        while target.exists():
            index+=1;target=root/f'attempt-{index}'
        return run(entry,case,target,policy,steps)
    return run_with_retry(attempt,previous)


def family(e,cfg,root):
    work=root/e['id'];completed=work/'family.json'
    if completed.exists():
        saved=read(completed)
        repaired=False
        for v in saved.get('variants',[]):
            meta=read(Path(v['case'])/'case.json')
            for name,key in [('checkpoint.cs','save_sha256'),('trial.rc','rc_sha256')]:
                if sha(Path(v['case'])/name)!=meta[key]: raise ValueError('Cached case changed')
            for i,row in enumerate(v['rows']):
                if retryable(row):
                    retried=policy_trial(dict(id=v['id'],seed=e['seed']),Path(v['case']),
                        work/'startup-retries'/Path(v['id']).name/row['option'].replace(':','-'),
                        row['option'],cfg['steps'],previous=row)
                    v['rows'][i]=verify_result(retried);repaired=True
            v['label']=classify(v['rows'])
        if repaired: write(completed,saved)
        return saved
    work.mkdir(parents=True,exist_ok=True)
    result=dict(id=e['id'],seed=e['seed'],split=e['split'],variants=[],status='quarantined')
    if not e['eligible']:
        result['reason']='Original checkpoint quarantined: '+str(e.get('error') or
            {'fidelity':e.get('fidelity'),'repeatability':e.get('repeatability')})
        write(completed,result);return result
    try:
        parent=Path(e['case']);meta=read(parent/'case.json')
        if not meta.get('training_ready') or meta['seed']!=e['seed']:
            raise ValueError('Unverified parent or seed mismatch')
        for name,key in [('checkpoint.cs','save_sha256'),('trial.rc','rc_sha256')]:
            if sha(parent/name)!=e[key] or meta[key]!=e[key]: raise ValueError('Parent changed')
        if meta['engine_sha256']!=sha(ROOT/cfg['parent_engine']): raise ValueError('Parent engine changed')
        # Preserve partial attempts rather than overwrite their evidence on resume.
        attempt=0
        while (work/f'attempt-{attempt}').exists(): attempt+=1
        task=work/f'attempt-{attempt}';task.mkdir()
        derived=derive(parent,task/'derived')
        refroot=task/'reference'
        subprocess.run([sys.executable,str(Path(__file__).resolve()),'--reference',
            str(derived),str(refroot),str(cfg['verify_steps'])],check=True,timeout=900,
            env={**os.environ,'DCSS_TACTICAL_ENGINE':str(ROOT/cfg['parent_engine']),
                 'DCSS_TACTICAL_AUGMENT':'0'},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        ref=read(refroot/'reference.json')
        neutral=task/'neutral-case';shutil.copytree(derived,neutral)
        nm=read(neutral/'case.json');nm['engine_sha256']=sha(ENGINE);write(neutral/'case.json',nm)
        result['neutral']=neutral_check(derived,neutral,task/'neutral',Path(ref['trace']))
        for i,recipe in enumerate(cfg['recipes']):
            ident=e['id']+f'/variant-{i:02d}';vroot=task/f'variant-{i:02d}';case=vroot/'case'
            make_variant(derived,case,recipe,e['id'])
            v=verify_variant(dict(id=ident,seed=e['seed'],family_id=e['id']),case,vroot,
                             recipe,ref['initial'],cfg['verify_steps'])
            v['split']=e['split'];v['rows']=[]
            if v['replay_verified']:
                for policy in POLICIES:
                    r=policy_trial(dict(id=ident,seed=e['seed']),case,vroot/policy.replace(':','-'),
                          policy,cfg['steps'])
                    r.update(phase='augmentation_dataset',split=e['split'],family_id=e['id'],
                             split_group=e['seed'],recipe=recipe,policy=policy)
                    v['rows'].append(verify_result(r))
            v['label']=classify(v['rows']);result['variants'].append(v)
            write(task/'progress.json',result)
        result['status']='generated' if all(v['replay_verified'] for v in result['variants']) else 'partial'
    except Exception as exc:
        result['reason']=repr(exc)
        if isinstance(exc,subprocess.CalledProcessError):
            result['reference_stderr']=exc.stderr.decode(errors='replace')
    write(completed,result);return result


def export(root,families):
    labels=[];training=[];cases=[];rows=[]
    for f in families:
        for v in f['variants']:
            checked=[verify_result(r) for r in v['rows']]
            label=classify(checked)
            admitted=bool(v['replay_verified'] and label['mixed'] and f['split']=='train')
            labels.append(dict(id=v['id'],seed=f['seed'],split=f['split'],
                family_id=f['id'],recipe=v['recipe'],case=v['case'],
                replay_verified=v['replay_verified'],training_selected=admitted,**label))
            rows+=checked
            if not admitted: continue
            meta=read(Path(v['case'])/'case.json')
            cases.append(dict(id=v['id'],case=v['case'],seed=f['seed'],split_group=f['seed'],
                split='train',family_id=f['id'],eligible=True,training_ready=True,
                save_sha256=meta['save_sha256'],rc_sha256=meta['rc_sha256'],
                engine_sha256=meta['engine_sha256'],recipe=v['recipe'],
                successful=label['successful'],failing=label['failing']))
            training += [r for r in checked if r['outcome'] in ('death','recovered_quiet')]
    # Keep the original corpus unchanged. This versioned supplement is consumable
    # by run_goals.fit via load_training(), never by concatenating unchecked files.
    write(root/'labels.json',labels);write(root/'results.json',rows)
    write(root/'training-rows.json',training)
    write(root/'training-index.json',dict(version=1,kind='synthetic goal-label supplement',
          cases=cases,manifest_sha256=sha(root/'manifest.json'),
          labels_sha256=sha(root/'labels.json'),rows_sha256=sha(root/'training-rows.json'),
          selection='Replay verified; all six labeled; audited success and death; train seed only'))
    summary=dict(encounters=len(families),coverage=dict(Counter(f['status'] for f in families)),
        variants=len(labels),verified_variants=sum(v['replay_verified'] for v in labels),
        trials=len(rows),outcomes=dict(Counter(r['outcome'] for r in rows)),
        mixed_variants=sum(v['mixed'] for v in labels),training_cases=len(cases),training_rows=len(training),
        training_seeds=sorted({e['seed'] for e in cases}),
        by_split={s:dict(variants=sum(v['split']==s for v in labels),
                         mixed=sum(v['split']==s and v['mixed'] for v in labels))
                  for s in sorted({f['split'] for f in families})},
        fitting=False,production_export=False)
    write(root/'summary.json',summary);return summary


def load_training(root):
    """Verified input to run_goals.fit; recipe/RNG metadata is never a feature."""
    root=Path(root);m=read(root/'manifest.json');index=read(root/'training-index.json')
    for n,h in m['sources'].items():
        if sha(HERE/n)!=h: raise ValueError('Controller source changed')
    if sha(ENGINE)!=m['engine_sha256']: raise ValueError('Engine changed')
    if sha(root/'manifest.json')!=index['manifest_sha256']: raise ValueError('Manifest changed')
    for name,key in [('labels.json','labels_sha256'),('training-rows.json','rows_sha256')]:
        if sha(root/name)!=index[key]: raise ValueError('Training labels changed')
    mapping=partition_map(read(ROOT/m['config']['partitions']))
    for path,h in m['inputs'].items():
        if sha(ROOT/path)!=h: raise ValueError('Dataset/split input changed')
    ids={e['id'] for e in index['cases']}
    for e in index['cases']:
        if mapping.get(e['seed'])!='train' or e['split_group']!=e['seed']:
            raise ValueError('Held-out seed in training')
        for name,key in [('checkpoint.cs','save_sha256'),('trial.rc','rc_sha256')]:
            if sha(Path(e['case'])/name)!=e[key]: raise ValueError('Synthetic case changed')
    rows=read(root/'training-rows.json')
    for r in rows:
        if (r['case_id'] not in ids or mapping.get(r['seed'])!='train' or r['split']!='train'
            or r['outcome'] not in ('death','recovered_quiet') or not r['evidence_verified']):
            raise ValueError('Invalid training row')
        if sha(Path(r['trace']))!=r['trace_sha256']: raise ValueError('Training trace changed')
    return rows


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--reference':
        reference(Path(sys.argv[2]),Path(sys.argv[3]),int(sys.argv[4]));return
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('config',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--resume',action='store_true')
    p.add_argument('--reuse',type=Path,help='New output; reuse completed verified families only when gameplay sources and inputs are unchanged')
    a=p.parse_args();cfg=read(a.config);root=a.output.resolve()
    if os.environ.get('DCSS_TACTICAL_AUGMENT')!='1' or ENGINE.name!='crawl-tactical-augment':
        raise ValueError('Explicit lab augmentation engine and opt-in required')
    if not cfg['recipes'] or len({json.dumps(r,sort_keys=True) for r in cfg['recipes']})!=len(cfg['recipes']):
        raise ValueError('Empty or duplicate recipes')
    for recipe in cfg['recipes']: validate_recipe(recipe)
    if not 1<=cfg['jobs']<=32 or not 1<=cfg['verify_steps']<=32 or cfg['steps']<1:
        raise ValueError('Invalid execution bounds')
    entries=inventory(cfg)
    inputs=[d['index'] for d in cfg['datasets']]+[cfg['partitions'],cfg['reservation']]
    manifest=dict(version=1,config=cfg,entries=entries,engine_sha256=sha(ENGINE),
        parent_engine_sha256=sha(ROOT/cfg['parent_engine']),
        inputs={n:sha(ROOT/n) for n in inputs},
        sources={n:sha(HERE/n) for n in SOURCES+('augmentation_dataset.py','augment_encounters.py','verify_resume.py','startup_retry.py')},
        fitting=False,production_export=False)
    if a.resume and a.reuse: raise ValueError('Choose resume or reuse, not both')
    if a.reuse:
        origin=a.reuse.resolve();compatible_cache(read(origin/'manifest.json'),manifest)
        manifest['reuse_manifest']=dict(path=str(origin/'manifest.json'),sha256=sha(origin/'manifest.json'))
    if a.resume:
        old=read(root/'manifest.json')
        if 'reuse_manifest' in old: manifest['reuse_manifest']=old['reuse_manifest']
        if read(root/'manifest.json')!=manifest: raise ValueError('Resume inputs or sources changed')
    else:
        root.mkdir(parents=True,exist_ok=False);write(root/'manifest.json',manifest)
    if a.reuse: print(json.dumps(dict(reused=reuse_families(origin,root,manifest))),flush=True)
    families=[]
    # Each worker owns its engine and JSON/geometry processing; avoid a shared
    # Python GIL across independent families in this CPU-heavy offline job.
    with ProcessPoolExecutor(max_workers=cfg['jobs']) as pool:
        fs=[pool.submit(family,e,cfg,root) for e in entries]
        for future in as_completed(fs):
            f=future.result();families.append(f);write(root/'coverage.json',families)
            print(json.dumps(dict(encounter=f['id'],status=f['status'],reason=f.get('reason'),
                  completed=len(families),total=len(entries))),flush=True)
    print(json.dumps(export(root,families)),flush=True)
    load_training(root)


if __name__=='__main__': main()
