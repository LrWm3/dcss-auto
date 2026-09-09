"""Screen verified training checkpoints for retreat failures and alternatives.

Data collection only: no model fitting, validation or test execution.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import random

from bench import ENGINE, sha
from dataset_splits import MANIFEST, partition_map
from train_encounters import run_episode, write
from train_options import OptionController
from train_replay import credit


def verify(entries,mapping):
    if not entries: raise ValueError('No eligible cases')
    if len({e['id'] for e in entries})!=len(entries): raise ValueError('Duplicate IDs')
    for e in entries:
        if mapping.get(e['seed'])!='train': raise ValueError('Training seeds only')
        if e['split_group']!=e['seed'] or not e['eligible']: raise ValueError('Unverified case')
        case=Path(e['case']);meta=json.loads((case/'case.json').read_text())
        if not meta.get('training_ready') or meta['seed']!=e['seed']: raise ValueError('Metadata mismatch')
        for filename,key in [('checkpoint.cs','save_sha256'),('trial.rc','rc_sha256')]:
            if sha(case/filename)!=e[key] or meta[key]!=e[key]: raise ValueError('Checkpoint hash mismatch')
        if e['engine_sha256']!=sha(ENGINE) or meta['engine_sha256']!=sha(ENGINE):
            raise ValueError('Engine mismatch')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('index',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--jobs',type=int,default=4)
    a=p.parse_args()
    if a.jobs<1: raise ValueError('Positive jobs required')
    index=json.loads(a.index.read_text());split=json.loads(MANIFEST.read_text())
    entries=[e for e in index['cases'] if e['eligible']]
    verify(entries,partition_map(split))
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
    cfg=dict(steps=600,turns=1500,handoff_steps=600,max_noops=8,hazard_shield=True,
             alpha=.03,gamma=1.,epsilon=.05)
    write(root/'config.json',cfg)
    write(root/'manifest.json',dict(index_sha256=sha(a.index),engine_sha256=sha(ENGINE),
        split=split,split_sha256=sha(MANIFEST),entries=entries,production_export=False,
        sources={n:sha(Path(__file__).parent/n) for n in
            ('screen_training_options.py','train_options.py','train_encounters.py','train_replay.py',
             'tactical_options.py','bench.py','mine_encounters.py')}))
    results=[]
    def run(entry,option,i):
        work=root/f'{option}-{i:03d}';work.mkdir()
        c=OptionController(fixed=option)
        r=run_episode(entry,work,option,{},random.Random(i),cfg,training=False,selector=c)
        if r['outcome']=='harness_error' or r.get('handoff',{}).get('outcome')=='harness_error':
            raise RuntimeError(str(r))
        r.update(audited_credit=credit(r),option=option,split='train',shield_overrides=c.overrides)
        write(work/'audited-result.json',r)
        write(work/'option-transition.json',dict(case_id=entry['id'],seed=entry['seed'],
            features=c.entry_features,option=option,credit=credit(r)))
        print(json.dumps(dict(case_id=entry['id'],option=option,credit=credit(r))),flush=True)
        return r
    def batch(tasks):
        with ThreadPoolExecutor(max_workers=a.jobs) as pool:
            futures=[pool.submit(run,e,o,i) for i,(e,o) in enumerate(tasks)]
            rows=[f.result() for f in futures]
        results.extend(rows);write(root/'results.json',results)
        return rows
    retreat=batch([(e,'retreat') for e in entries])
    failures={r['case_id'] for r in retreat if r['audited_credit']<=0}
    batch([(e,o) for e in entries if e['id'] in failures for o in ('hold','rage_hold','baseline')])
    contrasts=[dict(case_id=id_,retreat_credit=next(r['audited_credit'] for r in retreat if r['case_id']==id_),
        successful_alternatives=[r['option'] for r in results
            if r['case_id']==id_ and r['option']!='retreat' and r['audited_credit']>0]) for id_ in sorted(failures)]
    write(root/'summary.json',dict(completed=True,cases=len(entries),trials=len(results),
        retreat_positive=sum(r['audited_credit']>0 for r in retreat),contrasts=contrasts,
        selection_bias='Alternatives only tested after nonpositive retreat; not a full option matrix.',
        production_export=False))


if __name__=='__main__': main()
