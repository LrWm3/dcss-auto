"""Fresh goal-controller trials, then training-only fitted outcome selection.

Does not reuse old labels. Validation follows a frozen model; test untouched.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import random
from bench import HERE,ENGINE,sha,Environment
from goal_env import derive,GoalEnvironment
from goal_controllers import Controller,Recovery,available,features
from train_encounters import load_cases,write,value

SOURCES=('goal_bridge.lua','goal_env.py','goal_controllers.py','run_goals.py','bench.py',
         'train_encounters.py','dataset_splits.py','experiment.py')

def normalized(s):
    out=dict(s)
    # Lua pairs() ordering is not monster identity or a gameplay difference.
    if 'monsters' in out:
        out['monsters']=sorted(out['monsters'].values(),key=lambda e:(e['x'],e['y'],e['name']))
    return out

def projection(s):
    return {k:v for k,v in normalized(s).items() if k not in
        ('goal_version','position','known','anchors','unseen','can_berserk','seq','messages')}

def options(s): return [g+':'+str(b) for g in available(s) for b in (0,1)]

def select(model,s):
    f=features(s)
    # Stable no-rage-first ties. Joint values permit goal/rage interactions.
    return max(options(s),key=lambda o:value(model,o,f))

def run(entry,case,root,option,steps=600,model=None):
    root.mkdir(parents=True,exist_ok=False)
    env=GoalEnvironment(root);r=dict(case_id=entry['id'],seed=entry['seed'],option=option,
        outcome='harness_error',decisions=0)
    try:
        s=env.reset(case);first=s['turn'];r['features']=features(s)
        r['available']=options(s)
        if model is not None: option=select(model,s);r['option']=option
        if option not in options(s):
            r['outcome']='masked';return r
        g,b=option.split(':');c=Controller(g,bool(int(b)));recovery=Recovery()
        noops=0; stagnant=0; counts=Counter()
        for i in range(steps):
            action=c(s);counts[action]+=1;t=env.step(action);r['decisions']=i+1
            if t.get('terminal')=='death': r['outcome']='death';s=t;break
            noops=noops+1 if t['turn']==s['turn'] else 0
            stagnant=stagnant+1 if (t['hp']==s['hp'] and t['floor']==s['floor'] and
                t['position']==s['position'] and t['monsters']==s['monsters']) else 0
            good=recovery.observe(s,t);s=t
            if good: r['outcome']='recovered_quiet';break
            if noops>=8: r['outcome']='no_turn_stall';break
            if stagnant>=80: r['outcome']='unresolved_stall';break
            if s['turn']-first>=1500: r['outcome']='budget_truncated';break
        else: r['outcome']='budget_truncated'
        r.update(final_floor=s.get('floor'),final_hp=s.get('hp'),quiet_turns=recovery.quiet,
            turns=s.get('turn',first)-first,events=c.events,actions=dict(counts),
            credit={'recovered_quiet':1.,'death':-1.}.get(r['outcome'],0.))
    except Exception as exc: r['error']=str(exc)
    finally:
        r['worker']=str(getattr(env,'work',root));env.close();write(root/'result.json',r)
    return r

def fit(rows,epochs=1500):
    if any(r.get('split')!='train' for r in rows): raise ValueError('Non-training row')
    usable=[r for r in rows if r['outcome'] not in ('masked','harness_error')]
    model={};rng=random.Random(42)
    for _ in range(epochs):
        rng.shuffle(usable)
        for r in usable:
            f=r['features'];o=r['option'];w=model.setdefault(o,{})
            error=r['credit']-value(model,o,f);rate=.08/max(1,sum(v*v for v in f.values()))
            for k,v in f.items(): w[k]=w.get(k,0)+rate*error*v
    return model

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--config',type=Path,default=HERE/'options-expanded-v1.json')
    p.add_argument('--limit',type=int);p.add_argument('--jobs',type=int,default=6)
    p.add_argument('--steps',type=int,default=600);p.add_argument('--train',action='store_true')
    a=p.parse_args();cfg=json.loads(a.config.read_text());(train,val),index=load_cases(cfg)
    if a.limit: train=train[:a.limit]
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
    write(root/'manifest.json',dict(version=1,train=train,validation=val if a.train else [],
        engine_sha256=sha(ENGINE),dataset_sha256=sha(index),steps=a.steps,
        sources={n:sha(HERE/n) for n in SOURCES},production_export=False,
        endpoint='full health, no observable threat/harm, 20 checked single quiet turns'))
    cases={};checks=[]
    def verify(i,e):
        derived=derive(e['case'],root/f'case-{i:03d}')
        snapshots=[]
        for repeat in range(2):
            env=GoalEnvironment(root/'verify');
            try:
                s=env.reset(derived);snapshots.append(s)
            finally: env.close()
        old=Environment(root/'verify-parent')
        try: original=old.reset(e['case'])
        finally: old.close()
        equal=projection(original)==projection(snapshots[0])
        repeated=normalized(snapshots[0])==normalized(snapshots[1])
        if not equal or not repeated: raise RuntimeError('Derived reset mismatch: '+e['id'])
        return derived,dict(case_id=e['id'],parent_projection=equal,repeatable=repeated)
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futures=[pool.submit(verify,i,e) for i,e in enumerate(train+(val if a.train else []))]
        for future in as_completed(futures):
            derived,check=future.result();cases[check['case_id']]=derived;checks.append(check)
            write(root/'reset-checks.json',checks);print(json.dumps(check),flush=True)
    results=[]
    def batch(phase,entries,model=None):
        tasks=[(e,o) for e in entries for o in (['selector'] if model is not None else
            [g+':'+str(b) for g in ('withdraw','defend','pursue') for b in (0,1)])]
        with ThreadPoolExecutor(max_workers=a.jobs) as pool:
            futures={pool.submit(run,e,cases[e['id']],root/f'{phase}-{i:03d}',o,a.steps,model):e
                for i,(e,o) in enumerate(tasks)}
            for future in as_completed(futures):
                r=future.result();r.update(phase=phase,split='validation' if phase.startswith('validation') else 'train')
                results.append(r);write(root/'results.json',results)
                print(json.dumps({k:r.get(k) for k in ('phase','case_id','option','outcome','decisions','error')}),flush=True)
        if any(r['outcome']=='harness_error' for r in results): raise RuntimeError('Harness errors: no training')
    batch('collect',train)
    if a.train:
        model=fit(results);write(root/'model.json',model);frozen=sha(root/'model.json')
        batch('train_check',train,model);batch('validation',val,model)
        batch('validation_controls',val)
        if sha(root/'model.json')!=frozen or json.loads((root/'model.json').read_text())!=model:
            raise AssertionError('Model changed')
        collected={(r['case_id'],r['option']):r for r in results if r['phase']=='collect'}
        agreement=[dict(case_id=r['case_id'],option=r['option'],
            same_outcome=r['outcome']==collected[r['case_id'],r['option']]['outcome'])
            for r in results if r['phase']=='train_check']
        write(root/'selector-repeat-checks.json',agreement)
    summary={phase:dict(Counter(r['outcome'] for r in results if r['phase']==phase))
        for phase in ('collect','train_check','validation','validation_controls')}
    write(root/'summary.json',summary);print(json.dumps(summary),flush=True)

if __name__=='__main__': main()
