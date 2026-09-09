"""Frozen V2 selector versus fixed pursuit on original held-out checkpoints.

No training, mutation, HP normalization, tuning or production deployment.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from augmentation_dataset import inventory, read, verify_result
from bench import HERE, ROOT, ENGINE, sha
from character_dataset import canonical
from check_rich_goals import original_projection
from goal_env import GoalEnvironment
from goal_controllers import Controller
from rich_features import features
from rich_goals import derive, run, select
from run_goals import SOURCES
from train_encounters import write


def family(task):
    e, root, model = task
    root = Path(root)/e['id']; root.mkdir(parents=True, exist_ok=False)
    result = dict(id=e['id'], seed=e['seed'], split=e['split'], status='failed', rows=[])
    envs = []
    try:
        parent = Path(e['case'])
        for name,key in [('checkpoint.cs','save_sha256'),('trial.rc','rc_sha256')]:
            if sha(parent/name) != e[key]: raise ValueError('Original checkpoint changed')
        if read(parent/'case.json')['engine_sha256'] != sha(ENGINE):
            raise ValueError('Wrong original engine')
        case = derive(parent, root/'rich-case')
        envs = [GoalEnvironment(root/f'verify-{i}') for i in range(3)]
        states = [env.reset(c) for env,c in zip(envs,[parent,case,case])]
        initial = states[1]
        controller = Controller('pursue',False)
        for step in range(13):
            assert original_projection(states[0]) == original_projection(states[1]) == original_projection(states[2])
            assert canonical(states[1]) == canonical(states[2])
            if step == 12 or states[0].get('terminal'): break
            action = controller(states[0]); states = [env.step(action) for env in envs]
        result.update(prefix_verified=True, prefix_steps=step, initial=initial,
                      verification_workers=[str(env.work) for env in envs])
        for env in envs: env.close()
        result['predicted_option'] = select(model, initial)
        for name,option in [('candidate','selector'),('pursue_no_berserk','pursue:0'),('pursue_berserk','pursue:1')]:
            r = verify_result(run(dict(id=e['id'], seed=e['seed']), case, root/name,
                                  option, 600, model if name=='candidate' else None))
            r.update(evaluator=name, split=e['split'], split_group=e['seed'])
            if 'features' in r and r['features'] != features(initial):
                raise ValueError('Trial initial features differ from verified snapshot')
            if name=='candidate' and r['option'] != result['predicted_option']:
                raise ValueError('Saved model selection mismatch')
            result['rows'].append(r); write(root/'progress.json', result)
        result['status'] = 'complete'
    except Exception as exc:
        result['error'] = repr(exc)
    finally:
        for env in envs: env.close()
    write(root/'family.json', result)
    print(dict(id=e['id'], status=result['status'], error=result.get('error'),
               outcomes={r['evaluator']:r['outcome'] for r in result['rows']}), flush=True)
    return result


def summarize(families):
    reports = {}
    for split in ('all','validation','test','evaluation_only'):
        fs = [f for f in families if split=='all' or f['split']==split]
        good = [f for f in fs if f['status']=='complete' and len(f['rows'])==3 and
                all(r.get('evidence_verified') and r['outcome'] in ('death','recovered_quiet')
                    for r in f['rows'])]
        reports[split] = dict(encounters=len(fs), comparable=len(good),
            excluded=len(fs)-len(good),
            outcomes={name:dict(Counter(r['outcome'] for f in fs for r in f['rows']
                                      if r['evaluator']==name))
                      for name in ('candidate','pursue_no_berserk','pursue_berserk')},
            paired_outcomes={name:dict(Counter(r['outcome'] for f in good for r in f['rows']
                                             if r['evaluator']==name))
                             for name in ('candidate','pursue_no_berserk','pursue_berserk')})
    return reports


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('model',type=Path); p.add_argument('output',type=Path)
    a = p.parse_args(); root = a.output.resolve()
    cfg = read(HERE/'character-training-v1.json')
    entries = [e for e in inventory(cfg) if e['eligible'] and
               e['split'] in ('validation','test','evaluation_only')]
    trained = read(a.model.parent/'manifest.json')
    if {e['seed'] for e in entries} & set(trained['training_seeds']):
        raise ValueError('Held-out seed overlaps model training')
    completed = read(a.model.parent/'completion.json')
    if sha(a.model) != completed['model_sha256']: raise ValueError('Candidate changed')
    root.mkdir(parents=True, exist_ok=False)
    paths = [a.model, ENGINE, HERE/'character-training-v1.json', ROOT/cfg['partitions'],
             ROOT/cfg['reservation'], HERE.parents[1]/'rcs/codex-autocrawl.rc']
    paths += [ROOT/d['index'] for d in cfg['datasets']]
    paths += [HERE/n for n in SOURCES+('rich_features.py','rich_goal_bridge.lua','rich_goals.py',
              'evaluate_rich_holdout.py','character_dataset.py','check_rich_goals.py','augmentation_dataset.py')]
    frozen = {str(path.resolve()):sha(path) for path in paths}
    write(root/'manifest.json', dict(entries=entries, frozen=frozen, fitting=False,
        production_export=False, mutated=False, hp_normalized=False,
        caveat='Held out of fitting; previously evaluated seeds are not a pristine new test'))
    write(root/'status.json', dict(status='running', encounters=len(entries)))
    families = []
    with ProcessPoolExecutor(max_workers=6) as pool:
        tasks = [(e,str(root),read(a.model)) for e in entries]
        for future in as_completed([pool.submit(family,t) for t in tasks]):
            families.append(future.result()); write(root/'coverage.json',families)
            write(root/'status.json',dict(status='running', finished=len(families),encounters=len(entries)))
    for path,digest in frozen.items():
        if sha(Path(path)) != digest: raise ValueError('Frozen input changed: '+path)
    for f in families:
        for i,r in enumerate(f['rows']):
            checked = verify_result(r)
            if r.get('trace_sha256') != checked.get('trace_sha256'): raise ValueError('Trial trace changed')
            f['rows'][i] = checked
    write(root/'coverage.json',families)
    summary = summarize(families); write(root/'summary.json',summary)
    write(root/'completion.json',dict(fitting=False, production_export=False, model_sha256=sha(a.model),
        finished=len(families), summary=summary))
    write(root/'status.json',dict(status='complete', finished=len(families)))
    print(summary,flush=True)


if __name__=='__main__': main()
