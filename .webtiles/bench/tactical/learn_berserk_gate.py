"""Train and evaluate a state-level berserk-now versus never gate."""
import argparse
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
import multiprocessing as mp
from pathlib import Path

import numpy as np

from action_env import ActionEnv,ACTIONS,fixed_action
from audit_action_episodes import audit
from goal_controllers import dist
from rich_features import values
from train_action_imitation import save_json
from learn_berserk_timing import fit_tree,predict
import bench

RULES=('never','near')
FEATURES=('hp_fraction','max_hp','xl','ac','ev','enemy_count','max_threat',
          'adjacent_count','nearest_distance','ranged_count','unique_count',
          'can_berserk','confused','poisoned','unseen','on_fire','berserk')


def gate_context(s):
    es=values(s.get('monsters'));details=values(s.get('enemy_details'));p=s.get('player',{})
    return [s['hp']/s['max_hp'],s['max_hp']/200,p.get('xl',0)/27,p.get('ac',0)/50,
        p.get('ev',0)/50,len(es)/8,max([e['threat'] for e in es],default=0)/3,
        sum(dist((e['x'],e['y']))<=1 for e in es)/8,
        min([dist((e['x'],e['y'])) for e in es],default=16)/16,
        sum(e.get('range',1)>1 for e in details)/8,
        sum(bool(e.get('is_unique')) for e in details)/8,
        float(bool(s.get('can_berserk'))),float(bool(s.get('confused'))),
        float(bool(s.get('poisoned'))),float(bool(s.get('unseen'))),
        float(bool(s.get('on_fire'))),float(bool(s.get('berserk')))]


def nearest(s):
    return min([dist((e['x'],e['y'])) for e in values(s.get('monsters'))],default=99)


def decision_state(worker):
    path=Path(worker)/'events.jsonl'
    with path.open() as stream:
        first=json.loads(next(stream))['initial_observation']
        s=first
        for line in stream:
            if s.get('can_berserk') and nearest(s)<=2:
                return s
            s=json.loads(line)['next_observation']
    if s.get('can_berserk') and nearest(s)<=2:
        return s
    return None


def load_rows(run):
    run=Path(run);trials=json.loads((run/'train-trials.json').read_text())
    by_key=defaultdict(dict)
    for row in trials:by_key[(row['family'],row['rng_offset'])][row['rule']]=row
    rows=[];missing=[]
    for key,pair in sorted(by_key.items()):
        if not all(rule in pair for rule in RULES):raise ValueError('Incomplete pair '+str(key))
        state=decision_state(pair['near']['worker'])
        if state is None:
            missing.append(key);continue
        rows.append(dict(family=key[0],rng_offset=key[1],features=gate_context(state),
            now=pair['near']['outcome']=='recovered_quiet',
            never=pair['never']['outcome']=='recovered_quiet',
            near_outcome=pair['near']['outcome'],never_outcome=pair['never']['outcome']))
    return rows,missing


def select(tree,state,margin=.05):
    p=predict(tree,np.asarray(gate_context(state)))
    # Tree columns are [never, near]. Withhold only on a clear never advantage;
    # ties keep the strong near baseline.
    return 'never' if p[0]>p[1]+margin else 'near'


def trial(task):
    config,root,index,tree=task
    env=ActionEnv(config,Path(root)/f'case-{index:03d}','train')
    used=False;choice=None;decision=None
    result=dict(case_index=index,outcome='harness_error')
    try:
        env.reset(seed=24000+index,options={'case_index':index})
        result.update(case_id=env.entry['id'],seed=env.entry['seed'],rng_offset=env.entry['rng_offset'],
            family=env.entry['family'])
        for _ in range(env.max_steps):
            mask=env.action_masks();s=env.state;d=nearest(s)
            activate=False
            if not used and mask[ACTIONS.index('berserk')] and d<=2:
                if decision is None:
                    decision=gate_context(s);choice=select(tree,s)
                activate=choice=='near'
            a=ACTIONS.index('berserk') if activate else fixed_action(s,mask,'pursue')
            _,_,done,truncated,_=env.step(a)
            if activate:used=True
            if done or truncated:break
        audit(env.transport.work/'episode.json')
        result.update(json.loads((env.transport.work/'episode.json').read_text()),choice=choice,
                      decision_features=decision,activated=used)
    except Exception as exc:
        result.update(error=repr(exc),worker=str(getattr(env.transport,'work','')))
    finally:
        env.close()
    save_json(Path(result['worker'])/'gate.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--training-run',required=True,type=Path,action='append')
    p.add_argument('--fresh-config',required=True,type=Path)
    p.add_argument('--fresh-run',required=True,type=Path)
    args=p.parse_args();root=args.fresh_run.resolve();root.mkdir(parents=True,exist_ok=False)
    loaded=[load_rows(run) for run in args.training_run]
    train=[row for rows,_ in loaded for row in rows]
    missing=[key for _,keys in loaded for key in keys]
    if len(train)<60:raise ValueError('Too few training decision states')
    x=np.asarray([r['features'] for r in train]);y=np.asarray([[r['never'],r['now']] for r in train],dtype=float)
    tree=fit_tree(x,y,depth=3,min_leaf=5)
    save_json(root/'model.json',dict(tree=tree,features=FEATURES,rules=RULES,margin=.05,
        training_run=[str(run.resolve()) for run in args.training_run],training_rows=len(train),missing=missing,
        target='paired full recovery; choose near on ties'))
    cfg=json.loads(args.fresh_config.read_text())
    entries=[e for e in cfg['cases'] if e['split']=='train']
    tasks=[(str(args.fresh_config.resolve()),str(root),i,tree) for i in range(len(entries))]
    results=[]
    with ProcessPoolExecutor(max_workers=6,mp_context=mp.get_context('spawn')) as pool:
        for future in as_completed([pool.submit(trial,t) for t in tasks]):
            r=future.result();results.append(r);save_json(root/'trials.json',results)
            if r['outcome']=='harness_error':print(json.dumps(r),flush=True)
    if len(results)!=len(entries) or any(r['outcome']=='harness_error' for r in results):
        raise RuntimeError('Incomplete gate evaluation')
    save_json(root/'summary.json',dict(outcomes=dict(Counter(r['outcome'] for r in results)),
        choices=dict(Counter(r['choice'] for r in results)),activated=sum(r['activated'] for r in results),
        decisions=len(results),training_rows=len(train)))
    print(json.dumps(json.loads((root/'summary.json').read_text())),flush=True)


if __name__=='__main__':main()
