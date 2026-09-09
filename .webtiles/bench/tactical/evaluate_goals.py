"""Frozen broader evaluation. No fitting, controller changes, or dataset writes."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
import copy
import json
from pathlib import Path
from bench import HERE,ROOT,ENGINE,Environment,sha
from goal_env import derive,GoalEnvironment
from run_goals import SOURCES,normalized,projection,run
from train_encounters import write

MODEL_SHA='1f2b9cf7f525191cb4b2bf0c724bb95efdd43a26cf16db56befb9089d1efb7f0'
REFERENCE_SHA='62180b36d5b095d0176ce2d1363c68a2a5a8659fa4ab8d4237b5aba458b8c5d3'

def select_cases(index,reference):
    used=reference['train']+reference['validation']
    ids={e['id'] for e in used};seeds={e['seed'] for e in used}
    return [dict(e,cohort='unseen_seed' if e['seed'] not in seeds else 'familiar_seed_new_case')
            for e in index['cases'] if e['eligible'] and e['id'] not in ids]

def select_fresh_cases(index,reference,reservation,partitions):
    reserved=set(reservation['evaluation_only'])
    used={e['seed'] for e in reference['train']+reference['validation']}
    used.update(s for group in ('train','validation','test') for s in partitions[group])
    if reserved & used: raise ValueError('Fresh seed overlaps existing development seeds')
    if reservation['model_sha256']!=MODEL_SHA: raise ValueError('Reservation model mismatch')
    entries=[dict(e,cohort='fresh_seed') for e in index['cases'] if e['eligible']]
    if not entries or any(e['seed'] not in reserved for e in entries):
        raise ValueError('Unreserved or empty fresh evaluation')
    if len({e['id'] for e in entries})!=len(entries): raise ValueError('Duplicate case ID')
    return entries

def check_entry(e):
    case=Path(e['case']);meta=json.loads((case/'case.json').read_text())
    if not meta.get('training_ready'): raise ValueError('Unverified original checkpoint')
    for file,key in [('checkpoint.cs','save_sha256'),('trial.rc','rc_sha256')]:
        if sha(case/file)!=e[key] or meta[key]!=e[key]: raise ValueError('Checkpoint hash mismatch')
    if e['engine_sha256']!=sha(ENGINE) or meta['engine_sha256']!=e['engine_sha256']:
        raise ValueError('Engine mismatch')
    if e['seed']!=meta['seed'] or e['seed']!=e['split_group']: raise ValueError('Seed mismatch')

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--jobs',type=int,default=6)
    p.add_argument('--revised-controllers',action='store_true',help='Explicitly evaluate changed controller sources; never fit weights')
    p.add_argument('--case-id',action='append',help='Restrict to exact unused case IDs for targeted regression tests')
    p.add_argument('--fresh-evaluation',action='store_true',help='Use the separately reserved, hash-pinned fresh encounter collection')
    a=p.parse_args()
    reference_path=HERE/'artifacts/goals-trained-v3/manifest.json'
    if sha(reference_path)!=REFERENCE_SHA: raise ValueError('Training manifest changed')
    reference=json.loads(reference_path.read_text())
    for name,digest in reference['sources'].items():
        if sha(HERE/name)!=digest and not a.revised_controllers: raise ValueError('Frozen source changed: '+name)
    model_path=HERE/'models/goal-selector-v1.json'
    if sha(model_path)!=MODEL_SHA: raise ValueError('Frozen model changed')
    model=json.loads(model_path.read_text());original=copy.deepcopy(model)
    index_path=HERE/'artifacts/development-dataset-v3/index.json'
    reservation_path=HERE/'fresh-evaluation-seeds-v1.json'
    if a.fresh_evaluation:
        index_path=HERE/'artifacts/mining-fresh-evaluation-v2/verified-dataset/index.json'
        evidence=json.loads((HERE/'evidence/mining-fresh-evaluation-v2.json').read_text())
        if sha(index_path)!=evidence['artifact_hashes']['verified-dataset/index.json']:
            raise ValueError('Fresh dataset changed')
        entries=select_fresh_cases(json.loads(index_path.read_text()),reference,
            json.loads(reservation_path.read_text()),json.loads((HERE/'dataset-split-v1.json').read_text()))
    else:
        if sha(index_path)!=reference['dataset_sha256']: raise ValueError('Dataset changed')
        entries=select_cases(json.loads(index_path.read_text()),reference)
    if a.case_id:
        if set(a.case_id)-{e['id'] for e in entries}: raise ValueError('Unknown/non-evaluation case ID')
        entries=[e for e in entries if e['id'] in a.case_id]
    for e in entries: check_entry(e)
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
    write(root/'manifest.json',dict(version=1,entries=entries,steps=600,
        reference_manifest_sha256=REFERENCE_SHA,model_sha256=MODEL_SHA,
        dataset_sha256=sha(index_path),engine_sha256=sha(ENGINE),
        sources={n:sha(HERE/n) for n in SOURCES+('evaluate_goals.py',)},
        fitting=False,production_export=False,
        revised_controllers=a.revised_controllers,reference_sources=reference['sources'],
        fresh_evaluation=a.fresh_evaluation,
        reservation_sha256=sha(reservation_path) if a.fresh_evaluation else None,
        reserved_test_executed=any(e['seed']=='83017004' for e in entries),
        cohort_note=('Prospectively reserved new seeds; baseline difficulty-selected D1-D7 encounters, not full-game performance.' if a.fresh_evaluation else
                     'Unseen means unused by this selector; historical encounters are not prospectively fresh seeds.')))
    checks=[];cases={}
    def verify(i,e):
        check=dict(case_id=e['id'],seed=e['seed'],cohort=e['cohort'],passed=False)
        try:
            derived=derive(e['case'],root/f'case-{i:03d}');snapshots=[]
            for repeat in range(2):
                env=GoalEnvironment(root/'verify')
                try: snapshots.append(env.reset(derived))
                finally: env.close()
            env=Environment(root/'verify-parent')
            try: parent=env.reset(e['case'])
            finally: env.close()
            check.update(parent_projection=projection(parent)==projection(snapshots[0]),
                         repeatable=normalized(snapshots[0])==normalized(snapshots[1]))
            check['passed']=check['parent_projection'] and check['repeatable']
            return derived,check
        except Exception as exc:
            check['error']=str(exc);return None,check
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        fs=[pool.submit(verify,i,e) for i,e in enumerate(entries)]
        for f in as_completed(fs):
            derived,check=f.result();checks.append(check)
            if check['passed']:cases[check['case_id']]=derived
            write(root/'reset-checks.json',checks);print(json.dumps(check),flush=True)
    results=[]
    tasks=[(e,policy) for e in entries if e['id'] in cases for policy in
           ['selector','withdraw:0','withdraw:1','defend:0','defend:1','pursue:0','pursue:1']]
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        fs={pool.submit(run,e,cases[e['id']],root/f'trial-{i:03d}',policy,600,
                        copy.deepcopy(model) if policy=='selector' else None):(e,policy)
            for i,(e,policy) in enumerate(tasks)}
        for f in as_completed(fs):
            e,policy=fs[f];r=f.result()
            r.update(phase=e['cohort'],cohort=e['cohort'],policy=policy,
                     split='evaluation_only',dataset_partition=('fresh_evaluation' if a.fresh_evaluation else
                         'test' if e['seed']=='83017004' else 'train'))
            results.append(r);write(root/'results.json',results)
            print(json.dumps({k:r.get(k) for k in ('cohort','case_id','policy','option','outcome','error')}),flush=True)
    if model!=original or sha(model_path)!=MODEL_SHA: raise ValueError('Model mutated')
    summary={cohort:{policy:dict(Counter(r['outcome'] for r in results
        if r['cohort']==cohort and r['policy']==policy)) for policy in sorted({r['policy'] for r in results})}
        for cohort in sorted({e['cohort'] for e in entries})}
    write(root/'summary.json',dict(results=summary,quarantined=[c for c in checks if not c['passed']],
        model_unchanged=True,complete=len(results)==7*len(entries)))
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
