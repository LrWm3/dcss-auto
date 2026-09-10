"""Outcome-trained timing rule chooser; all non-berserk actions remain pursuit."""
import argparse
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
import multiprocessing as mp
from pathlib import Path
import numpy as np
from action_env import ActionEnv,ACTIONS,fixed_action
from audit_action_episodes import audit
from rich_features import values
from goal_controllers import dist
from train_action_imitation import save_json
import bench

RULES=('never','contact','near','late')
FEATURES=('hp_fraction','max_hp','xl','ac','ev','enemy_count','max_threat',
          'adjacent_count','nearest_distance','ranged_count','unique_count','can_berserk')


def context(s):
    es=values(s.get('monsters'));details=values(s.get('enemy_details'));p=s.get('player',{})
    return [s['hp']/s['max_hp'],s['max_hp']/200,p.get('xl',0)/27,p.get('ac',0)/50,
        p.get('ev',0)/50,len(es)/8,max([e['threat'] for e in es],default=0)/3,
        sum(dist((e['x'],e['y']))<=1 for e in es)/8,
        min([dist((e['x'],e['y'])) for e in es],default=16)/16,
        sum(e.get('range',1)>1 for e in details)/8,
        sum(bool(e.get('is_unique')) for e in details)/8,float(bool(s.get('can_berserk')))]


def trigger(rule,s,mask,used):
    if used or rule=='never' or not mask[ACTIONS.index('berserk')]:return False
    nearest=min([dist((e['x'],e['y'])) for e in values(s.get('monsters'))],default=99)
    return nearest<=({'contact':1,'near':2,'late':1}[rule]) and (rule!='late' or s['hp']/s['max_hp']<=.7)


def trial(task):
    config,root,split,index,rule=task
    env=ActionEnv(config,Path(root)/split/rule/f'case-{index:03d}',split)
    used=False;activations=[];result=dict(split=split,case_index=index,rule=rule,outcome='harness_error')
    try:
        env.reset(seed=18000+index,options={'case_index':index})
        result.update(features=context(env.state),case_id=env.entry['id'],seed=env.entry['seed'],
            rng_offset=env.entry['rng_offset'],family=env.entry['family'])
        for _ in range(env.max_steps):
            mask=env.action_masks()
            activate=trigger(rule,env.state,mask,used)
            a=ACTIONS.index('berserk') if activate else fixed_action(env.state,mask,'pursue')
            before=env.state
            _,_,done,truncated,_=env.step(a)
            if activate:
                used=True
                activations.append(dict(turn=before['turn'],hp=before['hp'],max_hp=before['max_hp'],
                                        no_op=env.state.get('turn',before['turn'])==before['turn']))
            if done or truncated:break
        audit(env.transport.work/'episode.json')
        result.update(json.loads((env.transport.work/'episode.json').read_text()))
    except Exception as exc:
        result.update(error=repr(exc),worker=str(getattr(env.transport,'work','')))
    finally:
        env.close()
    result['activations']=activations
    save_json(Path(result['worker'])/'timing.json',result)
    return result


def matrix(config,root,split):
    count=sum(e['split']==split for e in json.loads(Path(config).read_text())['cases'])
    tasks=[(config,str(root),split,i,r) for r in RULES for i in range(count)]
    results=[]
    with ProcessPoolExecutor(max_workers=6,mp_context=mp.get_context('spawn')) as pool:
        for future in as_completed([pool.submit(trial,t) for t in tasks]):
            r=future.result();results.append(r);save_json(root/(split+'-trials.json'),results)
            if len(results)%24==0 or r['outcome']=='harness_error':
                print(json.dumps(dict(split=split,completed=len(results),total=len(tasks),
                    outcomes=dict(Counter(x['outcome'] for x in results)))),flush=True)
    if any(r['outcome']=='harness_error' for r in results):
        raise RuntimeError('Incomplete outcome matrix: harness errors are not gameplay labels')
    return results


def fit_tree(x,y,depth=2,min_leaf=3):
    node=dict(value=y.mean(axis=0).tolist(),families=len(x))
    if depth==0 or len(x)<2*min_leaf:return node
    best=None;initial=float(((y-y.mean(axis=0))**2).sum())
    for feature in range(x.shape[1]):
        unique=np.unique(x[:,feature])
        for threshold in (unique[:-1]+unique[1:])/2:
            left=x[:,feature]<=threshold
            if min(left.sum(),(~left).sum())<min_leaf:continue
            loss=sum(float(((v-v.mean(axis=0))**2).sum()) for v in (y[left],y[~left]))
            if best is None or loss<best[0]-1e-12:best=(loss,feature,float(threshold),left)
    if best is not None and best[0]<initial-1e-12:
        _,feature,threshold,left=best
        node.update(feature=feature,threshold=threshold,
            left=fit_tree(x[left],y[left],depth-1,min_leaf),right=fit_tree(x[~left],y[~left],depth-1,min_leaf))
    return node


def predict(tree,x):
    while 'feature' in tree:tree=tree['left'] if x[tree['feature']]<=tree['threshold'] else tree['right']
    return np.asarray(tree['value'])


def choose(tree,x):
    p=predict(tree,x);best=int(p.argmax())
    return RULES[best] if p[best]-p[0]>=.1-1e-12 else 'never'


def grouped(rows):
    groups=defaultdict(list)
    for r in rows:groups[r['family']].append(r)
    names=sorted(groups);x=[];y=[]
    for name in names:
        records=groups[name];features=records[0]['features']
        if any(r['features']!=features for r in records):raise ValueError('RNG-dependent initial features')
        if len({r['seed'] for r in records})!=1:raise ValueError('Expected one seed per family')
        x.append(features)
        offsets={r['rng_offset'] for r in records}
        if len(records)!=len(offsets)*len(RULES):raise ValueError('Incomplete family matrix')
        y.append([sum(r['outcome']=='recovered_quiet' for r in records if r['rule']==rule)/len(offsets) for rule in RULES])
    return names,np.asarray(x),np.asarray(y),groups


def selected(rows,choices):
    chosen=[r for r in rows if r['rule']==choices[r['family']]]
    return dict(outcomes=dict(Counter(r['outcome'] for r in chosen)),
                rules=dict(Counter(r['rule'] for r in chosen)),cases=len(chosen))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    config=str(args.config.resolve());cfg=json.loads(args.config.read_text())
    if cfg.get('test_used') or not cfg.get('preflight_passed'):raise ValueError('Invalid config')
    (root/'sources').mkdir();sources=['learn_berserk_timing.py','action_env.py','goal_controllers.py','audit_action_episodes.py']
    for name in sources:(root/'sources'/name).write_bytes((bench.HERE/name).read_bytes())
    save_json(root/'manifest.json',dict(config=config,config_sha256=bench.sha(args.config),rules=RULES,
        features=FEATURES,max_activations=1,max_steps=192,tree_depth=2,min_leaf_families=3,
        min_predicted_advantage=.1,outcome_target='full recovery probability; deaths and budgets not successes',
        sources={n:bench.sha(bench.HERE/n) for n in sources},test_used=False,production_export=False,
        choice='One timing rule from initial observable context; rule checked every action.'))
    train=matrix(config,root,'train');names,x,y,groups=grouped(train)
    # Each family is one seed. Hold out all its RNG siblings together.
    choices={}
    for i,name in enumerate(names):
        keep=np.arange(len(names))!=i
        choices[name]=choose(fit_tree(x[keep],y[keep]),x[i])
    tree=fit_tree(x,y);save_json(root/'model.json',dict(tree=tree,features=FEATURES,rules=RULES))
    save_json(root/'family-outcomes.json',[dict(family=n,probabilities=dict(zip(RULES,y[i])),
        crossfit_rule=choices[n],fitted_rule=choose(tree,x[i])) for i,n in enumerate(names)])
    train_summary=dict(baselines={r:dict(Counter(v['outcome'] for v in train if v['rule']==r)) for r in RULES},
        crossfit=selected(train,choices),fitted=selected(train,{n:choose(tree,x[i]) for i,n in enumerate(names)}))
    save_json(root/'training-summary.json',train_summary);print(json.dumps(train_summary),flush=True)
    # Frozen model; validation outcomes never affect the fitted tree or choice.
    validation=matrix(config,root,'validation');vn,vx,_,_=grouped(validation)
    vc={n:choose(tree,vx[i]) for i,n in enumerate(vn)}
    summary=dict(training=train_summary,validation=dict(
        baselines={r:dict(Counter(v['outcome'] for v in validation if v['rule']==r)) for r in RULES},
        learned=selected(validation,vc),choices=vc))
    save_json(root/'summary.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
