"""Verify timing execution, paired matrices and training-only model fitting."""
import argparse
import json
from collections import Counter
from pathlib import Path
import numpy as np
import bench
from action_env import ACTIONS, fixed_action
from audit_action_episodes import audit
from learn_berserk_timing import RULES, FEATURES, context, trigger, grouped, fit_tree, choose, selected


def verify(root):
    root=Path(root)
    manifest=json.loads((root/'manifest.json').read_text())
    for name,expected in manifest['sources'].items():
        if bench.sha(bench.HERE/name)!=expected or bench.sha(root/'sources'/name)!=expected:
            raise ValueError('Source changed: '+name)
    if bench.sha(Path(manifest['config']))!=manifest['config_sha256']:
        raise ValueError('Config changed')
    train=json.loads((root/'train-trials.json').read_text())
    validation=json.loads((root/'validation-trials.json').read_text())
    config=json.loads(Path(manifest['config']).read_text())
    if {r['seed'] for r in train}&{r['seed'] for r in validation}:
        raise ValueError('Seed leakage')
    decisions=activations=0
    for split,rows in [('train',train),('validation',validation)]:
        expected_keys={(e['family'],e['rng_offset'],rule) for e in config['cases']
                       if e['split']==split for rule in RULES}
        keys=[(r['family'],r['rng_offset'],r['rule']) for r in rows]
        if len(set(keys))!=len(keys) or set(keys)!=expected_keys:
            raise ValueError('Incomplete or duplicate paired trial')
        for r in rows:
            if r['split']!=split:raise ValueError('Wrong split')
            worker=Path(r['worker'])
            if audit(worker/'episode.json')!=r['outcome']:raise ValueError('Outcome mismatch')
            events=[json.loads(s) for s in (worker/'events.jsonl').read_text().splitlines()]
            actions=[json.loads(s) for s in (worker/'actions.jsonl').read_text().splitlines()]
            state=events[0]['initial_observation'];used=False;observed=[]
            if context(state)!=r['features']:raise ValueError('Context mismatch')
            for event,row in zip(events[1:],actions):
                activate=trigger(r['rule'],state,row['mask'],used)
                expected=ACTIONS.index('berserk') if activate else fixed_action(state,row['mask'],'pursue')
                if ACTIONS[expected]!=row['action']:raise ValueError('Controller/action mismatch')
                after=event['next_observation']
                if activate:
                    used=True;activations+=1
                    observed.append(dict(turn=state['turn'],hp=state['hp'],max_hp=state['max_hp'],
                        no_op=after.get('turn',state['turn'])==state['turn']))
                state=after;decisions+=1
            if observed!=r['activations']:raise ValueError('Activation mismatch')
    names,x,y,_=grouped(train)
    tree=fit_tree(x,y)
    model=json.loads((root/'model.json').read_text())
    if model!=dict(tree=tree,features=list(FEATURES),rules=list(RULES)):
        raise ValueError('Model mismatch')
    crossfit={}
    for i,name in enumerate(names):
        keep=np.arange(len(names))!=i
        crossfit[name]=choose(fit_tree(x[keep],y[keep]),x[i])
    summary=json.loads((root/'summary.json').read_text())
    expected_train=dict(baselines={rule:dict(Counter(r['outcome'] for r in train if r['rule']==rule)) for rule in RULES},
        crossfit=selected(train,crossfit),fitted=selected(train,{n:choose(tree,x[i]) for i,n in enumerate(names)}))
    if summary['training']!=expected_train:raise ValueError('Training summary mismatch')
    vn,vx,_,_=grouped(validation)
    choices={n:choose(tree,vx[i]) for i,n in enumerate(vn)}
    expected_val=dict(baselines={rule:dict(Counter(r['outcome'] for r in validation if r['rule']==rule)) for rule in RULES},
        learned=selected(validation,choices),choices=choices)
    if summary['validation']!=expected_val:raise ValueError('Validation summary mismatch')
    return dict(episodes=len(train)+len(validation),decisions=decisions,activations=activations,
                training_families=len(names),validation_families=len(vn))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path)
    print(json.dumps(verify(p.parse_args().root)))
