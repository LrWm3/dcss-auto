"""Frozen evaluation of conservative rage selection; no fitting or deployment."""
import argparse
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import random

from bench import ENGINE, ROOT, sha
from conservative_options import ConservativeController, select_option
from train_encounters import features, load_cases, run_episode, validate, value, write
from train_options import OptionController
from train_options_expanded import metrics, progress, same_checkpoint, SOURCES
from train_replay import credit


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('config',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();cfg=json.loads(a.config.read_text());validate(cfg)
    (train,validation),index=load_cases(cfg)
    source=(ROOT/cfg['source_run']).resolve()
    for name,key in [('manifest.json','source_manifest_sha256'),('model.json','source_model_sha256'),
                     ('training-outcomes.json','source_labels_sha256')]:
        if sha(source/name)!=cfg[key]: raise ValueError('Source changed: '+name)
    manifest=json.loads((source/'manifest.json').read_text());oldcfg=json.loads((source/'config.json').read_text())
    if manifest['dataset_sha256']!=sha(index) or manifest['engine_sha256']!=sha(ENGINE):
        raise ValueError('Source dataset/engine mismatch')
    for name in SOURCES:
        if manifest['sources'][name]!=sha(Path(__file__).parent/name): raise ValueError('Source code changed: '+name)
    for name in ('steps','turns','handoff_steps','hazard_shield','split_provenance'):
        if cfg[name]!=oldcfg[name]: raise ValueError('Task changed: '+name)
    for entries,key in [(train,'train'),(validation,'validation')]:
        originals={e['id']:e for e in manifest[key]}
        if {e['id'] for e in entries}!=set(originals):raise ValueError('Changed cases')
        if any(not same_checkpoint(e,originals[e['id']]) for e in entries):raise ValueError('Changed checkpoint')
    ref=(ROOT/cfg['imitation_model']).resolve()
    if sha(ref)!=cfg['imitation_sha256'] or sha(ref.parent/'manifest.json')!=cfg['imitation_manifest_sha256']:
        raise ValueError('Imitation changed')
    model=json.loads((source/'model.json').read_text());imitation=json.loads(ref.read_text())
    labels=json.loads((source/'training-outcomes.json').read_text())
    bykey={(r['case_id'],r['option']):r for r in labels}
    if len(bykey)!=len(train)*4 or any(r['case_id'] not in {e['id'] for e in train} for r in labels):
        raise ValueError('Training labels incomplete or leak')
    # This audit uses training labels only; freeze margin before validation.
    audit=[]
    for e in train:
        f=bykey[e['id'],'retreat']['features'];choice=select_option(model,f,cfg['berserk_margin'])
        audit.append(dict(case_id=e['id'],**choice,
            expected_credit=bykey[e['id'],choice['option']]['credit']))
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
    write(root/'config.json',cfg);write(root/'training-selection-audit.json',audit)
    write(root/'manifest.json',dict(engine_sha256=sha(ENGINE),dataset_sha256=sha(index),
        model_sha256=sha(source/'model.json'),training_labels_sha256=sha(source/'training-outcomes.json'),
        train=train,validation=validation,production_export=False,
        sources={n:sha(Path(__file__).parent/n) for n in SOURCES+
                 ('train_options_expanded.py','conservative_options.py','evaluate_conservative_options.py')}))
    results=[]
    def run(phase,e,policy,weights,i):
        work=root/f'{phase}-{policy}-{i:03d}';work.mkdir();before=copy.deepcopy(weights)
        c=ConservativeController(weights,cfg['berserk_margin']) if policy=='selector' else OptionController(fixed='retreat' if policy=='imitation' else policy)
        def select(state,memory,allowed):
            if policy=='imitation':
                f=features(state,memory);return max(allowed,key=lambda a:value(weights,a,f))
            return c(state,memory,allowed)
        r=run_episode(e,work,policy,weights,random.Random(i),cfg,training=False,selector=select)
        if before!=weights:raise AssertionError('Frozen model changed')
        if r['outcome']=='harness_error' or r.get('handoff',{}).get('outcome')=='harness_error':raise RuntimeError(str(r))
        end=r.get('handoff',{}).get('final_floor')
        if 'handoff' not in r:
            last=None
            with (Path(r['worker'])/'transitions.jsonl').open() as stream:
                for line in stream:last=line
            if last:end=json.loads(last)['next_observation'].get('floor')
        r.update(phase=phase,split='train' if e in train else 'validation',audited_credit=credit(r),
            selected_option=c.option,selection=getattr(c,'selection',None),
            **progress(e['initial']['floor'],end))
        write(work/'audited-result.json',r)
        print(json.dumps({k:r[k] for k in ('phase','case_id','policy','selected_option','audited_credit','final_floor')}),flush=True)
        return r
    def batch(phase,tasks):
        with ThreadPoolExecutor(max_workers=cfg['jobs']) as pool:
            futures=[pool.submit(run,phase,e,p,copy.deepcopy(m),i) for i,(e,p,m) in enumerate(tasks)]
            results.extend(f.result() for f in futures)
        write(root/'results.json',results)
    batch('train_check',[(e,'selector',model) for e in train])
    batch('validation',[(e,p,m) for e in validation for p,m in
        [('selector',model),('retreat',{}),('baseline',{}),('imitation',imitation)]
        for _ in range(cfg['eval_repeats'])])
    write(root/'summary.json',dict(completed=True,trials=len(results),production_export=False,
        model_sha256=sha(source/'model.json'),berserk_margin=cfg['berserk_margin'],
        groups=[dict(phase=phase,policy=policy,**metrics([r for r in results if r['phase']==phase and r['policy']==policy]))
                for phase,policy in sorted({(r['phase'],r['policy']) for r in results})]))


if __name__=='__main__':main()
