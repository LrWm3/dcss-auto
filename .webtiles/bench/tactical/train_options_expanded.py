"""Complete a hash-checked option matrix, fit once, then evaluate frozen policies."""
import argparse
import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import random

from bench import ENGINE, ROOT, sha
from dataset_splits import partition_map
from train_encounters import features, load_cases, run_episode, validate, value, write
from train_options import OPTIONS, OptionController, fit
from train_replay import credit

SOURCES=('train_options.py','train_encounters.py','train_replay.py','tactical_options.py','bench.py','mine_encounters.py')


def labels_hash(root):
    h=hashlib.sha256()
    for path in sorted(root.glob('*/option-transition.json')):
        h.update(str(path.relative_to(root)).encode());h.update(b'\0');h.update(path.read_bytes())
    return h.hexdigest()


def same_checkpoint(a,b):
    return all(a[k]==b[k] for k in ('seed','save_sha256','rc_sha256','engine_sha256'))


def cached_rows(specs,train,cfg):
    bypath={str(Path(e['case']).resolve()):e for e in train};accepted={};provenance=[]
    for spec in specs:
        root=(ROOT/spec['root']).resolve()
        for name,key in [('manifest.json','manifest_sha256'),('results.json','results_sha256')]:
            if sha(root/name)!=spec[key]: raise ValueError('Cache hash mismatch: '+name)
        if labels_hash(root)!=spec['labels_sha256']: raise ValueError('Cached labels changed')
        manifest=json.loads((root/'manifest.json').read_text());oldcfg=json.loads((root/'config.json').read_text())
        if manifest['engine_sha256']!=sha(ENGINE): raise ValueError('Cache engine mismatch')
        for name in SOURCES:
            if manifest['sources'][name]!=sha(Path(__file__).parent/name):
                raise ValueError('Cache source mismatch: '+name)
        for name,default in [('steps',600),('turns',1500),('handoff_steps',0),('max_noops',8),('hazard_shield',False)]:
            if oldcfg.get(name,default)!=cfg.get(name,default): raise ValueError('Cache task mismatch: '+name)
        entries={e['id']:e for e in manifest.get('train',manifest.get('entries',[]))}
        for r in json.loads((root/'results.json').read_text()):
            if r.get('phase') not in (None,'collect'): continue
            old=entries.get(r['case_id'])
            if old is None: raise ValueError('Cache result not in training manifest')
            e=bypath.get(str(Path(old['case']).resolve()))
            if e is None: continue
            if not same_checkpoint(e,old): raise ValueError('Cache checkpoint mismatch')
            rowpath=Path(r['worker']).parent/'option-transition.json'
            if root not in rowpath.resolve().parents: raise ValueError('Cache path outside root')
            row=json.loads(rowpath.read_text());option=row['option']
            if option not in OPTIONS or option!=r['policy'] or row['seed']!=e['seed']:
                raise ValueError('Cache option/seed mismatch')
            if row['credit']!=credit(r) or r['audited_credit']!=credit(r): raise ValueError('Cache credit mismatch')
            key=(e['id'],option)
            if key in accepted: raise ValueError('Duplicate cached option')
            if not row['features']: raise ValueError('Missing entry features')
            accepted[key]=dict(row,case_id=e['id'],source=str(rowpath),cached=True)
            provenance.append(dict(case_id=e['id'],option=option,path=str(rowpath),sha256=sha(rowpath)))
    return accepted,provenance


def metrics(rows):
    return dict(count=len(rows),positive=sum(r['audited_credit']>0 for r in rows),
        deaths=sum(r['audited_credit']<0 for r in rows),
        neutral=sum(r['audited_credit']==0 for r in rows),
        floor_changes=sum(r['floor_changed'] for r in rows),
        deeper_same_branch=sum(r['deeper_same_branch'] for r in rows),
        recovered_without_floor_change=sum(r['audited_credit']>0 and not r['floor_changed'] for r in rows))


def progress(start,end):
    changed=end is not None and start!=end
    try:
        a,x=start.split(':');b,y=end.split(':')
        deeper=a==b and int(y)>int(x)
    except (AttributeError,ValueError): deeper=False
    return dict(initial_floor=start,final_floor=end,floor_changed=changed,deeper_same_branch=deeper)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('config',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();cfg=json.loads(a.config.read_text());validate(cfg)
    if cfg['evaluation_mode']!='held_out' or not cfg.get('hazard_shield'): raise ValueError('Held-out shield required')
    for k in ('jobs','fit_epochs'):
        if type(cfg.get(k)) is not int or cfg[k]<1: raise ValueError(k)
    (train,validation),index=load_cases(cfg)
    cached,provenance=cached_rows(cfg['caches'],train,cfg)
    ref=(ROOT/cfg['imitation_model']).resolve()
    if sha(ref)!=cfg['imitation_sha256'] or sha(ref.parent/'manifest.json')!=cfg['imitation_manifest_sha256']:
        raise ValueError('Reference hash mismatch')
    refmanifest=json.loads((ref.parent/'manifest.json').read_text())
    assignment=partition_map(cfg['split_provenance']['manifest'])
    current={str(Path(e['case']).resolve()):e for e in train}
    for e in refmanifest['train']:
        match=current.get(str(Path(e['case']).resolve()))
        if assignment[e['seed']]!='train' or match is None or not same_checkpoint(match,e):
            raise ValueError('Reference is not a training-only subset')
    if refmanifest['engine_sha256']!=sha(ENGINE): raise ValueError('Reference engine mismatch')
    for name in ('bench.py','train_encounters.py','tactical_options.py','mine_encounters.py'):
        if refmanifest['sources'][name]!=sha(Path(__file__).parent/name): raise ValueError('Reference source mismatch')
    imitation=json.loads(ref.read_text())
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
    write(root/'config.json',cfg)
    write(root/'manifest.json',dict(dataset_sha256=sha(index),engine_sha256=sha(ENGINE),
        train=train,validation=validation,cached_labels=provenance,imitation_sha256=sha(ref),
        sources={n:sha(Path(__file__).parent/n) for n in SOURCES+('train_options_expanded.py',)},
        production_export=False))
    results=[]

    def run(phase,e,policy,model,i):
        work=root/f'{phase}-{policy}-{i:03d}';work.mkdir();before=copy.deepcopy(model)
        c=OptionController(model,fixed=policy if policy in OPTIONS else None)
        def select(state,memory,allowed):
            if policy=='imitation':
                f=features(state,memory)
                return max(allowed,key=lambda a:value(model,a,f))
            return c(state,memory,allowed)
        r=run_episode(e,work,policy,model,random.Random(cfg['random_seed']+i),cfg,training=False,selector=select)
        if before!=model: raise AssertionError('Evaluation mutated weights')
        if r['outcome']=='harness_error' or r.get('handoff',{}).get('outcome')=='harness_error': raise RuntimeError(str(r))
        end=r.get('handoff',{}).get('final_floor')
        if 'handoff' not in r:
            last=None
            with (Path(r['worker'])/'transitions.jsonl').open() as stream:
                for line in stream: last=line
            if last: end=json.loads(last)['next_observation'].get('floor')
        r.update(phase=phase,split='train' if e in train else 'validation',audited_credit=credit(r),
                 selected_option=c.option,**progress(e['initial']['floor'],end))
        row=dict(case_id=e['id'],seed=e['seed'],option=c.option,features=c.entry_features,credit=credit(r),cached=False)
        write(work/'audited-result.json',r);write(work/'option-transition.json',row)
        print(json.dumps({k:r[k] for k in ('phase','split','case_id','policy','selected_option','audited_credit','final_floor')}),flush=True)
        return r,row

    def batch(phase,tasks):
        rows=[]
        with ThreadPoolExecutor(max_workers=cfg['jobs']) as pool:
            futures=[pool.submit(run,phase,e,p,copy.deepcopy(m),i) for i,(e,p,m) in enumerate(tasks)]
            for future in futures:
                r,row=future.result();results.append(r);rows.append(row)
        write(root/'results.json',results)
        return rows

    missing=[(e,p,{}) for e in train for p in OPTIONS if (e['id'],p) not in cached]
    new=batch('collect',missing)
    rows=list(cached.values())+new
    expected={(e['id'],o) for e in train for o in OPTIONS}
    if {(r['case_id'],r['option']) for r in rows}!=expected or len(rows)!=len(expected):
        raise ValueError('Incomplete option matrix')
    write(root/'training-outcomes.json',rows)
    model=fit(rows,cfg['fit_epochs']);write(root/'model.json',model)
    # Actual frozen selector replays on all training cases, including D7 and new contrasts.
    batch('train_check',[(e,'selector',model) for e in train])
    batch('validation',[(e,p,m) for e in validation for p,m in
        [('selector',model),('retreat',{}),('baseline',{}),('imitation',imitation)]
        for _ in range(cfg['eval_repeats'])])
    groups=[dict(phase=phase,policy=policy,**metrics([r for r in results if r['phase']==phase and r['policy']==policy]))
        for phase,policy in sorted({(r['phase'],r['policy']) for r in results})]
    write(root/'summary.json',dict(completed=True,new_trials=len(results),cached_outcomes=len(cached),
        training_cases=len(train),training_outcomes=len(rows),groups=groups,
        training_mse=sum((value(model,r['option'],r['features'])-r['credit'])**2 for r in rows)/len(rows),
        model_sha256=sha(root/'model.json'),production_export=False))


if __name__=='__main__': main()
