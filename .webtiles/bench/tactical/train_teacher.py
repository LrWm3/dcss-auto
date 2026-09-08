"""Retreat demonstrations -> linear imitation initialisation -> online Q pilot.

Held-out seeds are used only by frozen evaluation. D7 training-case checks are
reported separately. Does not export or deploy a production policy.
"""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import random

from bench import ENGINE, sha
from tactical_options import Tactic
from train_encounters import load_cases, validate, write, run_episode, value


def imitate(samples, epochs=100, margin=1.):
    """Deterministic multiclass margin updates over legal actions only."""
    if not samples: raise ValueError('No successful teacher samples')
    model={}
    for epoch in range(epochs):
        rows=list(samples);random.Random(epoch).shuffle(rows)
        for row in rows:
            f=row['features'];target=row['action'];allowed=row['allowed']
            if target not in allowed: raise ValueError('Masked teacher action')
            alternatives=[a for a in allowed if a!=target]
            if not alternatives: continue
            other=max(alternatives,key=lambda a:value(model,a,f))
            loss=margin+value(model,other,f)-value(model,target,f)
            if loss<=0: continue
            rate=min(.1,loss/(2*max(1.,sum(v*v for v in f.values()))))
            for a,sign in ((target,1),(other,-1)):
                weights=model.setdefault(a,{})
                for k,v in f.items(): weights[k]=weights.get(k,0)+sign*rate*v
    accuracy=sum(max(r['allowed'],key=lambda a:value(model,a,r['features']))==r['action']
                 for r in samples)/len(samples)
    return model,accuracy


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('config',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();cfg=json.loads(a.config.read_text());validate(cfg)
    if cfg['evaluation_mode']!='held_out': raise ValueError('Held-out seeds required')
    if type(cfg.get('jobs',4)) is not int or cfg.get('jobs',4)<1: raise ValueError('Bad jobs')
    (train,evaluation),index=load_cases(cfg)
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
    write(root/'config.json',cfg)
    write(root/'manifest.json',dict(dataset_sha256=sha(index),engine_sha256=sha(ENGINE),
        sources={n:sha(Path(__file__).parent/n) for n in
                 ('train_teacher.py','train_encounters.py','tactical_options.py','bench.py','mine_encounters.py')},
        train=train,evaluation=evaluation,production_export=False))
    results=[];samples=[]

    def run(phase,entry,policy,model,number,training=False,collector=None):
        work=root/f'{phase}-{number:03d}';work.mkdir()
        before=copy.deepcopy(model)
        r=run_episode(entry,work,policy,model,random.Random(cfg.get('random_seed',0)+number),cfg,
                      training=training,epsilon=cfg['epsilon'],
                      controller=Tactic('retreat') if policy=='retreat' else None,samples=collector)
        if not training and model!=before: raise AssertionError('Evaluation mutated model')
        r.update(phase=phase,split='train' if entry in train else 'held_out')
        print(json.dumps(r),flush=True)
        if r['outcome']=='harness_error' or r.get('handoff',{}).get('outcome')=='harness_error':
            raise RuntimeError('Harness error: '+str(r))
        return r

    def evaluate(phase,model,policies):
        tasks=[(entry,policy) for entry in train+evaluation for policy in policies
               for _ in range(cfg['eval_repeats'])]
        with ThreadPoolExecutor(max_workers=cfg.get('jobs',4)) as pool:
            futures=[pool.submit(run,phase,e,p,copy.deepcopy(model),i) for i,(e,p) in enumerate(tasks)]
            for f in futures: results.append(f.result())
        write(root/'results.json',results)

    for i,entry in enumerate(train):
        rows=[];r=run('teacher',entry,'retreat',{},i,collector=rows);results.append(r)
        # A bad demonstration is evidence, not an imitation target.
        if r['outcome']=='safe_recovery' and r.get('handoff',{}).get('outcome') not in ('death','no_turn_stall'):
            samples.extend(rows)
    write(root/'demonstrations.json',samples)
    model,accuracy=imitate(samples)
    write(root/'initial-model.json',dict(weights=model,training_action_accuracy=accuracy,production_export=False))
    evaluate('initial',model,('baseline','retreat','q'))
    for i in range(cfg['episodes']):
        results.append(run('train',train[i%len(train)],'q',model,i,training=True))
        write(root/'model.json',dict(weights=model,production_export=False))
        write(root/'results.json',results)
    evaluate('final',model,('q',))
    summary=dict(completed=True,demonstrations=len(samples),training_action_accuracy=accuracy,
                 initial_model_sha256=sha(root/'initial-model.json'),model_sha256=sha(root/'model.json'),
                 results=[{k:r[k] for k in ('phase','split','case_id','policy','outcome','decisions','handoff') if k in r}
                          for r in results])
    write(root/'summary.json',summary)
    return 0


if __name__=='__main__': raise SystemExit(main())
