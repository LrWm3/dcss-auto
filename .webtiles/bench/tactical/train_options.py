"""One encounter-level decision: a small full-feedback contextual bandit.

Collect every option on training checkpoints, fit linear audited outcome values,
then freeze and compare. No online switching, validation fitting, or deployment.
"""
import argparse
import copy
import json
import random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bench import ENGINE, ROOT, sha
from tactical_options import Tactic
from train_encounters import features, load_cases, run_episode, validate, value, write
from train_replay import credit

OPTIONS=('retreat','hold','rage_hold','baseline')


def fit(rows,epochs=1000):
    if not rows: raise ValueError('No training outcomes')
    model={}
    for epoch in range(epochs):
        batch=list(rows);random.Random(epoch).shuffle(batch)
        for row in batch:
            a=row['option'];f=row['features']
            if a not in OPTIONS: raise ValueError('Unknown option')
            error=row['credit']-value(model,a,f)
            rate=.1/max(1.,sum(x*x for x in f.values()))
            w=model.setdefault(a,{})
            for k,x in f.items(): w[k]=w.get(k,0.)+rate*error*x
    return model


class OptionController:
    def __init__(self,model=None,fixed=None):
        if fixed is not None and fixed not in OPTIONS: raise ValueError(fixed)
        self.model=model or {};self.fixed=fixed;self.option=None
        self.entry_features=None;self.tactic=None;self.overrides=0

    def __call__(self,state,memory,allowed):
        if self.tactic is None:
            self.entry_features=features(state,memory)
            self.option=self.fixed or max(OPTIONS,key=lambda a:value(self.model,a,self.entry_features))
            self.tactic=Tactic(self.option)
        action=self.tactic(state)
        if action not in allowed:
            self.overrides+=1;return 'baseline'
        return action


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('config',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();cfg=json.loads(args.config.read_text());validate(cfg)
    if cfg['evaluation_mode']!='held_out' or not cfg.get('hazard_shield') or not cfg.get('handoff_steps'):
        raise ValueError('Held-out evaluation, shield and followup required')
    for k in ('jobs','fit_epochs'):
        if type(cfg.get(k)) is not int or cfg[k]<1: raise ValueError(k)
    (train,evaluation),index=load_cases(cfg)
    reference=(ROOT/cfg['imitation_model']).resolve()
    if sha(reference)!=cfg['imitation_sha256']: raise ValueError('Imitation hash mismatch')
    imitation=json.loads(reference.read_text())
    # Validate reference provenance too: it must use the same training cases,
    # partitions, engine and adapter, not merely have a matching model hash.
    manifest=json.loads((reference.parent/'manifest.json').read_text())
    oldcfg=json.loads((reference.parent/'config.json').read_text())
    if ({e['id'] for e in manifest['train']}!={e['id'] for e in train}
            or manifest['dataset_sha256']!=sha(index) or manifest['engine_sha256']!=sha(ENGINE)):
        raise ValueError('Reference training provenance differs')
    for key in ('steps','turns','handoff_steps','hazard_shield','split_provenance'):
        if oldcfg.get(key)!=cfg.get(key): raise ValueError('Reference config differs: '+key)
    for name in ('train_encounters.py','tactical_options.py','bench.py','mine_encounters.py'):
        if manifest['sources'][name]!=sha(Path(__file__).parent/name):
            raise ValueError('Reference source differs: '+name)
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    write(root/'config.json',cfg)
    write(root/'manifest.json',dict(engine_sha256=sha(ENGINE),dataset_sha256=sha(index),
        imitation_sha256=sha(reference),reference_manifest_sha256=sha(reference.parent/'manifest.json'),
        sources={n:sha(Path(__file__).parent/n) for n in
            ('train_options.py','train_encounters.py','train_replay.py','tactical_options.py','bench.py','mine_encounters.py')},
        train=train,validation=evaluation,production_export=False))
    results=[];training_rows=[]

    def run(phase,entry,policy,model,number):
        work=root/f'{phase}-{policy}-{number:03d}';work.mkdir()
        before=copy.deepcopy(model)
        controller=OptionController(model,fixed=policy if policy in OPTIONS else None)
        def select(state,memory,allowed):
            if policy=='imitation':
                f=features(state,memory)
                return max(allowed,key=lambda a:value(model,a,f))
            return controller(state,memory,allowed)
        r=run_episode(entry,work,policy,model,random.Random(cfg['random_seed']+number),
                      cfg,training=False,selector=select)
        if model!=before: raise AssertionError('Rollout changed weights')
        if r['outcome']=='harness_error' or r.get('handoff',{}).get('outcome')=='harness_error':
            raise RuntimeError(str(r))
        r.update(phase=phase,split='train' if entry in train else 'validation',
                 audited_credit=credit(r),selected_option=controller.option,
                 shield_overrides=controller.overrides)
        row=dict(case_id=entry['id'],seed=entry['seed'],features=controller.entry_features,
                 option=controller.option,credit=credit(r))
        write(work/'audited-result.json',r);write(work/'option-transition.json',row)
        print(json.dumps(r),flush=True)
        return r,row

    def batch(phase,tasks):
        rows=[]
        with ThreadPoolExecutor(max_workers=cfg['jobs']) as pool:
            futures=[pool.submit(run,phase,e,p,copy.deepcopy(m),i) for i,(e,p,m) in enumerate(tasks)]
            for future in futures:
                r,row=future.result();results.append(r);rows.append(row)
        write(root/'results.json',results)
        return rows

    training_rows=batch('collect',[(e,p,{}) for e in train for p in OPTIONS])
    write(root/'training-outcomes.json',training_rows)
    model=fit(training_rows,cfg['fit_epochs'])
    write(root/'model.json',model)
    batch('evaluate',[(e,p,m) for e in train+evaluation
        for p,m in [('selector',model),('retreat',{}),('imitation',imitation)]
        for _ in range(cfg['eval_repeats'])])
    groups=[]
    for key in sorted({(r['phase'],r['split'],r['policy']) for r in results}):
        rows=[r for r in results if (r['phase'],r['split'],r['policy'])==key]
        groups.append(dict(phase=key[0],split=key[1],policy=key[2],count=len(rows),
            credits=dict(Counter(r['audited_credit'] for r in rows)),
            selected_options=dict(Counter(r['selected_option'] for r in rows)),
            outcomes=dict(Counter(r['outcome'] for r in rows)),
            handoffs=dict(Counter(r['handoff']['outcome'] for r in rows if 'handoff' in r))))
    write(root/'summary.json',dict(completed=True,trials=len(results),groups=groups,
        training_mse=sum((value(model,r['option'],r['features'])-r['credit'])**2 for r in training_rows)/len(training_rows),
        production_export=False))


if __name__=='__main__': main()
