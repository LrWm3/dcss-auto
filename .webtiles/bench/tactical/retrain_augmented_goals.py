"""Fit once on verified synthetic training rows; evaluate frozen recorded choices.

This is outcome-supervised training of the existing linear selector, not new
per-turn RL. No deployment, hyperparameter search, or held-out fitting.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from augmentation_dataset import read, load_training, verify_result
from bench import HERE, sha
from run_goals import fit, run
from train_encounters import value, write


def choice(model, rows):
    first=rows[0]
    if any(r['features']!=first['features'] or r['available']!=first['available'] for r in rows):
        raise ValueError('Policy initial features or masks differ')
    return max(first['available'],key=lambda o:value(model,o,first['features']))


def evaluate(model, baseline, rows):
    groups=defaultdict(list)
    for r in rows: groups[r['case_id']].append(r)
    selections=[]
    for ident,rs in sorted(groups.items()):
        by={r['option']:r for r in rs}
        if len(by)!=6: raise ValueError('Incomplete policy matrix')
        picks={'candidate':choice(model,rs),'baseline':choice(baseline,rs),
               'pursue_no_berserk':'pursue:0','pursue_berserk':'pursue:1'}
        selections.append(dict(case_id=ident,seed=rs[0]['seed'],split=rs[0]['split'],
            choices={name:dict(option=o,outcome=by[o]['outcome']) for name,o in picks.items()}))
    summary={split:{name:dict(Counter(s['choices'][name]['outcome'] for s in selections
                      if s['split']==split)) for name in picks}
             for split in sorted({s['split'] for s in selections})}
    return selections,summary


def live(task):
    entry,case,root,model=task
    r=run(entry,Path(case),Path(root),'selector',600,model)
    return verify_result(r)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('dataset',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--live-checks',type=int,default=6)
    a=p.parse_args();root=a.output.resolve();dataset=a.dataset.resolve()
    if a.live_checks<0: raise ValueError('Negative live check count')
    training=load_training(dataset)
    # Pin the full matrix to the committed collection audit, not just its train subset.
    evidence=read(HERE/'evidence/augmentation-all-v4.json')
    for name in ('manifest.json','results.json','labels.json','coverage.json'):
        if sha(dataset/name)!=evidence['artifact_sha256'][name]:
            raise ValueError('Collection evidence mismatch: '+name)
    baseline_path=HERE/'models/goal-selector-v1.json';baseline_hash=sha(baseline_path)
    root.mkdir(parents=True,exist_ok=False)
    write(root/'manifest.json',dict(dataset=str(dataset),
        dataset_manifest_sha256=sha(dataset/'manifest.json'),
        training_rows_sha256=sha(dataset/'training-rows.json'),
        matrix_sha256=sha(dataset/'results.json'),baseline_sha256=baseline_hash,
        script_sha256=sha(Path(__file__)),epochs=1500,random_seed=42,
        training_rows=len(training),training_cases=len({r['case_id'] for r in training}),
        training_seeds=sorted({r['seed'] for r in training}),
        policy='One fixed fit; synthetic mixed training only; old controller labels not reused',
        evaluation='Recorded exhaustive outcomes on all variants; no held-out tuning',
        production_export=False))
    model=fit(sorted(training,key=lambda r:(r['case_id'],r['option'])))
    write(root/'model.json',model);frozen=sha(root/'model.json')
    rows=read(dataset/'results.json')
    selections,summary=evaluate(model,read(baseline_path),rows)
    train_ids={r['case_id'] for r in training}
    summary['selected_training_fit']=dict(Counter(s['choices']['candidate']['outcome']
        for s in selections if s['case_id'] in train_ids))
    write(root/'selections.json',selections);write(root/'summary.json',summary)
    print(summary,flush=True)
    # Deterministic smoke sample of changed held-out choices, selected without
    # examining whether those choices win or lose. Labels remain frozen.
    changed=[s for s in selections if s['split']!='train' and
             s['choices']['candidate']['option']!=s['choices']['baseline']['option']]
    sample=changed[:a.live_checks]
    cases={v['id']:v['case'] for f in read(dataset/'coverage.json') for v in f['variants']}
    tasks=[(dict(id=s['case_id'],seed=s['seed']),cases[s['case_id']],str(root/f'live-{i:03d}'),model)
           for i,s in enumerate(sample)]
    checks=[]
    if tasks:
        with ProcessPoolExecutor(max_workers=min(6,len(tasks))) as pool:
            for s,r in zip(sample,pool.map(live,tasks)):
                expected=s['choices']['candidate']
                checks.append(dict(case_id=s['case_id'],expected=expected,result=r,
                    passed=r['option']==expected['option'] and r['outcome']==expected['outcome']
                           and r.get('evidence_verified',False)))
                write(root/'live-checks.json',checks)
                print(dict(case_id=s['case_id'],live_check=checks[-1]['passed']),flush=True)
    else: write(root/'live-checks.json',checks)
    if sha(root/'model.json')!=frozen or sha(baseline_path)!=baseline_hash:
        raise ValueError('Frozen model changed')
    write(root/'completion.json',dict(model_sha256=frozen,live_checks=len(checks),
        live_passed=sum(c['passed'] for c in checks),held_out_variants=sum(s['split']!='train' for s in selections),
        held_out_changed_choices=len(changed),production_export=False))
    if any(not c['passed'] for c in checks): raise RuntimeError('Live replay discrepancy; do not deploy')


if __name__=='__main__': main()
