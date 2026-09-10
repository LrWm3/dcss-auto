"""Train a cost-aware state-level berserk-now versus never gate."""
import argparse
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
import multiprocessing as mp
from pathlib import Path

import numpy as np

from action_env import ActionEnv,ACTIONS,fixed_action
from audit_action_episodes import audit
from learn_berserk_gate import FEATURES,decision_state,gate_context,nearest
from learn_berserk_timing import fit_tree,predict
from train_action_imitation import save_json

RULES=('never','near')
OUTCOME_VALUE={'recovered_quiet':100.0,'budget_truncated':0.0,'no_turn_stall':0.0,'death':-100.0}


def utility(row,cost=2.0):
    if row['outcome'] not in OUTCOME_VALUE:
        raise ValueError('Unknown outcome: '+row['outcome'])
    used=row.get('activations',row.get('activated',False))
    return OUTCOME_VALUE[row['outcome']]-cost*bool(used)


def load_rows(runs,cost=2.0):
    by_key=defaultdict(dict);missing=[]
    for run in runs:
        for row in json.loads((Path(run)/'train-trials.json').read_text()):
            by_key[(row['family'],row['rng_offset'])][row['rule']]=row
    rows=[]
    for key,pair in sorted(by_key.items()):
        if not all(rule in pair for rule in RULES):raise ValueError('Incomplete pair '+str(key))
        state=decision_state(pair['near']['worker'])
        if state is None:
            missing.append(key);continue
        rows.append(dict(family=key[0],rng_offset=key[1],features=gate_context(state),
            utility_never=utility(pair['never'],cost),utility_near=utility(pair['near'],cost),
            never_outcome=pair['never']['outcome'],near_outcome=pair['near']['outcome'],
            near_activated=bool(pair['near'].get('activations'))))
    return rows,missing


def select(tree,state,margin=0.0):
    values=predict(tree,np.asarray(gate_context(state)))
    # Columns are [never, near]. Cost is already in the targets; require a
    # strict advantage so a utility tie does not spend berserk.
    return 'near' if values[1]>values[0]+margin else 'never'


def trial(task):
    config,root,index,tree=task
    env=ActionEnv(config,Path(root)/f'case-{index:03d}','train')
    used=False;choice=None;decision=None
    result=dict(case_index=index,outcome='harness_error')
    try:
        env.reset(seed=26000+index,options={'case_index':index})
        result.update(case_id=env.entry['id'],seed=env.entry['seed'],rng_offset=env.entry['rng_offset'],
            family=env.entry['family'])
        for _ in range(env.max_steps):
            mask=env.action_masks();state=env.state
            if not used and mask[ACTIONS.index('berserk')] and nearest(state)<=2:
                if decision is None:
                    decision=gate_context(state);choice=select(tree,state)
                activate=choice=='near'
            else:
                activate=False
            action=ACTIONS.index('berserk') if activate else fixed_action(state,mask,'pursue')
            _,_,done,truncated,_=env.step(action)
            if activate:used=True
            if done or truncated:break
        audit(env.transport.work/'episode.json')
        episode=json.loads((env.transport.work/'episode.json').read_text())
        result.update(episode,choice=choice,decision_features=decision,activated=used)
        result['utility']=utility(result,cost=2.0)
    except Exception as exc:
        result.update(error=repr(exc),worker=str(getattr(env.transport,'work','')))
    finally:
        env.close()
    save_json(Path(result['worker'])/'cost-gate.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--training-run',required=True,type=Path,action='append')
    p.add_argument('--fresh-config',required=True,type=Path)
    p.add_argument('--fresh-run',required=True,type=Path)
    p.add_argument('--cost',type=float,default=2.0)
    args=p.parse_args();root=args.fresh_run.resolve();root.mkdir(parents=True,exist_ok=False)
    if args.cost!=2.0:raise ValueError('The first pass is fixed at cost=2.0')
    train,missing=load_rows(args.training_run,args.cost)
    if len(train)<100:raise ValueError('Too few cost-aware training states')
    x=np.asarray([r['features'] for r in train])
    y=np.asarray([[r['utility_never'],r['utility_near']] for r in train],dtype=float)
    tree=fit_tree(x,y,depth=3,min_leaf=5)
    save_json(root/'model.json',dict(tree=tree,features=FEATURES,rules=RULES,cost=args.cost,
        outcome_value=OUTCOME_VALUE,training_runs=[str(r.resolve()) for r in args.training_run],
        training_rows=len(train),missing=missing))
    cfg=json.loads(args.fresh_config.read_text());entries=[e for e in cfg['cases'] if e['split']=='train']
    tasks=[(str(args.fresh_config.resolve()),str(root),i,tree) for i in range(len(entries))]
    results=[]
    with ProcessPoolExecutor(max_workers=6,mp_context=mp.get_context('spawn')) as pool:
        for future in as_completed([pool.submit(trial,t) for t in tasks]):
            result=future.result();results.append(result);save_json(root/'trials.json',results)
            if result['outcome']=='harness_error':print(json.dumps(result),flush=True)
    if len(results)!=len(entries) or any(r['outcome']=='harness_error' for r in results):
        raise RuntimeError('Incomplete cost-aware gate evaluation')
    summary=dict(outcomes=dict(Counter(r['outcome'] for r in results)),
        choices=dict(Counter(r['choice'] for r in results)),activated=sum(r['activated'] for r in results),
        utility=sum(r['utility'] for r in results),decisions=len(results),training_rows=len(train))
    save_json(root/'summary.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
