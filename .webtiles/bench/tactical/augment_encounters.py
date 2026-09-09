"""Recipe-backed offline encounter augmentation; no fitting or original writes.

Each reset copies the immutable parent save, then applies a one-shot HP/RNG
recipe before the first observation. Synthetic checkpoints require the separate
lab engine and explicit DCSS_TACTICAL_AUGMENT=1 opt-in. Families remain seed-grouped.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shutil

from bench import HERE, ENGINE, sha
from goal_env import GoalEnvironment
from goal_controllers import Controller
from run_goals import SOURCES, run
from verify_resume import normalized
from train_encounters import write

POLICIES = [g+':'+str(b) for g in ('withdraw','defend','pursue') for b in (0,1)]


def validate_recipe(recipe):
    if set(recipe) != {'hp_percent','rng_draws'}:
        raise ValueError('Recipe requires only HP percentage and RNG draw count')
    for key, low, high in [('hp_percent',1,100),('rng_draws',0,100000)]:
        if type(recipe[key]) is not int or not low <= recipe[key] <= high:
            raise ValueError('Invalid '+key)


def wrapper(recipe):
    validate_recipe(recipe)
    return '''
-- Explicit synthetic recipe, applied once per process before observation.
local augmentation_ready = ready
local augmentation_applied = false
function ready()
  if not augmentation_applied then
    you.tactical_augment(%d, %d)
    augmentation_applied = true
  end
  augmentation_ready()
end
''' % (recipe['hp_percent'], recipe['rng_draws'])


def make_variant(parent, destination, recipe, family):
    validate_recipe(recipe)
    meta=json.loads((parent/'case.json').read_text())
    for name,key in [('checkpoint.cs','save_sha256'),('trial.rc','rc_sha256')]:
        if sha(parent/name)!=meta[key]: raise ValueError('Parent checksum mismatch')
    if meta.get('goal_version')!=1: raise ValueError('Enhanced goal checkpoint required')
    source=(parent/'trial.rc').read_text()
    if 'you.tactical_augment(' in source: raise ValueError('Cannot augment an augmented parent')
    at=source.rfind('\n>')
    if at<0: raise ValueError('No Lua block')
    destination.mkdir(parents=True,exist_ok=False)
    shutil.copy2(parent/'checkpoint.cs',destination/'checkpoint.cs')
    (destination/'trial.rc').write_text(source[:at]+wrapper(recipe)+source[at:])
    meta.update(parent_case=str(parent),parent_engine_sha256=meta['engine_sha256'],
        parent_rc_sha256=meta['rc_sha256'],engine_sha256=sha(ENGINE),
        rc_sha256=sha(destination/'trial.rc'),augmentation=recipe,
        family_id=family,split_group=meta['seed'],split='evaluation_only',
        training_ready=False,replay_verified=False,
        checkpoint_kind='immutable parent save plus one-shot reset recipe')
    write(destination/'case.json',meta)
    return meta


def startup(env, case):
    """Retry only the known pre-observation map-parser failure; preserve workers."""
    errors=[]
    for attempt in range(2):
        try: return env.reset(case),errors
        except Exception as exc:
            terminal=env.work/'terminal.txt'
            known=terminal.exists() and 'regret_index_lairdec_grave_grove' in terminal.read_text()
            errors.append(dict(worker=str(env.work),error=str(exc),known_startup_error=known))
            env.close()
            if not known or attempt: raise


def rollout(env, case, steps):
    s,errors=startup(env,case); states=[s]; c=Controller('pursue',False)
    for _ in range(steps):
        if s.get('terminal'): break
        s=env.step(c(s));states.append(s)
    return states,errors


def verify_variant(entry, case, root, recipe, initial, steps):
    result=dict(id=entry['id'],seed=entry['seed'],family_id=entry['family_id'],
        split_group=entry['seed'],split='evaluation_only',case=str(case),recipe=recipe,
        replay_verified=False,training_ready=False,workers=[],startup_errors=[])
    trajectories=[]
    try:
        for repeat in range(2):
            env=GoalEnvironment(root)
            try:
                states,errors=rollout(env,case,steps)
                result['startup_errors']+=errors
                result['workers'].append(str(env.work));trajectories.append(states)
            finally: env.close()
        a,b=trajectories
        result['repeatable']=[normalized(s) for s in a]==[normalized(s) for s in b]
        expected=normalized(initial); expected['hp']=max(1,initial['max_hp']*recipe['hp_percent']//100)
        result['mutation_exact']=normalized(a[0])==expected
        result['replay_verified']=result['repeatable'] and result['mutation_exact']
        result['initial']=a[0]
        result['trace_sha256']=[sha(Path(w)/'transitions.jsonl') for w in result['workers']]
        result['prefix_states']=len(a)
        meta=json.loads((case/'case.json').read_text())
        meta.update(replay_verified=result['replay_verified'],observation=a[0])
        write(case/'case.json',meta)
    except Exception as exc: result['error']=str(exc)
    write(root/'verification.json',result)
    print(json.dumps({k:result.get(k) for k in ('id','replay_verified','mutation_exact','repeatable','error')}),flush=True)
    return result


def neutral_check(parent, case, root, reference):
    rows=[json.loads(line) for line in reference.read_text().splitlines()][:32]
    if not rows: raise ValueError('Empty neutral reference')
    env=GoalEnvironment(root)
    try:
        s,errors=startup(env,case)
        if normalized(s)!=normalized(rows[0]['observation']):
            raise ValueError('Neutral initial state differs')
        for i,row in enumerate(rows):
            s=env.step(row['action'])
            if normalized(s)!=normalized(row['next_observation']):
                raise ValueError('Neutral engine trajectory differs at '+str(i))
        return dict(passed=True,decisions=len(rows),reference=str(reference),
            reference_sha256=sha(reference),worker=str(env.work),startup_errors=errors,
            trace_sha256=sha(env.work/'transitions.jsonl'))
    finally: env.close()


def prepare(cfg, root):
    if os.environ.get('DCSS_TACTICAL_AUGMENT')!='1': raise ValueError('Explicit augmentation opt-in required')
    if ENGINE.name!='crawl-tactical-augment': raise ValueError('Separate augmentation lab engine required')
    for recipe in cfg['recipes']: validate_recipe(recipe)
    families=[]
    for f in cfg['families']:
        origin=HERE/f['benchmark'];m=json.loads((origin/'manifest.json').read_text())
        pairs=[(i,e) for i,e in enumerate(m['entries']) if e['id']==f['case_id']]
        if len(pairs)!=1: raise ValueError('Missing/ambiguous family')
        i,e=pairs[0];parent=origin/f'case-{i:03d}'
        results=json.loads((origin/'results.json').read_text())
        ref=next(r for r in results if r['case_id']==f['case_id'] and r['policy']=='pursue:0')
        families.append(dict(f,seed=e['seed'],parent=str(parent.resolve()),
            original_initial=e['initial'],reference=str(Path(ref['worker'])/'transitions.jsonl'),
            parent_save_sha256=sha(parent/'checkpoint.cs'),parent_rc_sha256=sha(parent/'trial.rc')))
    manifest=dict(version=1,config=cfg,families=families,engine_sha256=sha(ENGINE),
        sources={n:sha(HERE/n) for n in SOURCES+('augment_encounters.py',)},
        fitting=False,production_export=False,split='evaluation_only',
        endpoint='full health, observable safety, 20 checked quiet single turns',
        note='Synthetic variants of inspected families; not independent seeds or held-out evidence.')
    write(root/'manifest.json',manifest)
    checks=[]
    for f in families:
        case=root/f['id']/'neutral-case'
        make_variant(Path(f['parent']),case,dict(hp_percent=100,rng_draws=0),f['id'])
        check=neutral_check(Path(f['parent']),case,root/f['id']/'neutral',Path(f['reference']))
        check['family_id']=f['id']; checks.append(check)
        write(root/'neutral-checks.json',checks);print(json.dumps(check),flush=True)
    tasks=[]
    for f in families:
        # Neutral initial includes full enhanced observations, not only summary fields.
        initial=json.loads(Path(f['reference']).read_text().splitlines()[0])['observation']
        for i,recipe in enumerate(cfg['recipes']):
            id_=f['id']+f'/variant-{i:02d}';work=root/id_;case=work/'case'
            make_variant(Path(f['parent']),case,recipe,f['id'])
            tasks.append((dict(id=id_,seed=f['seed'],family_id=f['id']),case,work,recipe,initial,cfg['verify_steps']))
    results=[]
    with ThreadPoolExecutor(max_workers=cfg['jobs']) as pool:
        futures=[pool.submit(verify_variant,*t) for t in tasks]
        for future in as_completed(futures):
            results.append(future.result());write(root/'variants.json',results)
    return results


def evaluate(cfg, root):
    m=json.loads((root/'manifest.json').read_text())
    if sha(ENGINE)!=m['engine_sha256']: raise ValueError('Engine changed')
    for n,v in m['sources'].items():
        if sha(HERE/n)!=v: raise ValueError('Source changed: '+n)
    variants=json.loads((root/'variants.json').read_text());rows=[]
    tasks=[(v,policy) for v in variants if v['replay_verified'] for policy in POLICIES]
    def trial(i,v,policy):
        r=run(v,Path(v['case']),root/f'trial-{i:03d}',policy,cfg['steps'])
        errors=[]
        if r['outcome']=='harness_error' and r['decisions']==0:
            terminal=Path(r['worker'])/'terminal.txt'
            if terminal.exists() and 'regret_index_lairdec_grave_grove' in terminal.read_text():
                errors.append(r)
                r=run(v,Path(v['case']),root/f'trial-{i:03d}-retry',policy,cfg['steps'])
        r.update(policy=policy,phase='augmentation_pilot',cohort='synthetic',
            family_id=v['family_id'],recipe=v['recipe'],split_group=v['seed'],
            split='evaluation_only',startup_attempts=errors)
        return r
    with ThreadPoolExecutor(max_workers=cfg['jobs']) as pool:
        fs=[pool.submit(trial,i,v,policy) for i,(v,policy) in enumerate(tasks)]
        for f in as_completed(fs):
            r=f.result();rows.append(r);write(root/'results.json',rows)
            print(json.dumps({k:r.get(k) for k in ('case_id','policy','outcome','error')}),flush=True)
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('config',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--phase',choices=['prepare','evaluate','all'],default='all')
    args=p.parse_args();cfg=json.loads(args.config.read_text());root=args.output.resolve()
    if args.phase in ('prepare','all'):
        root.mkdir(parents=True,exist_ok=False);write(root/'config.json',cfg);prepare(cfg,root)
    elif cfg!=json.loads((root/'config.json').read_text()): raise ValueError('Config changed')
    if args.phase in ('evaluate','all'):evaluate(cfg,root)


if __name__=='__main__':main()
