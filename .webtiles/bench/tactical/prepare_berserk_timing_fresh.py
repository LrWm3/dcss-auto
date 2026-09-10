"""Derive a fresh RNG-offset config for outcome-based berserk timing."""
import argparse
import json
import multiprocessing as mp
import re
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import bench
from prepare_action_pilot import verify


def advance_hook(source, offset):
    pattern=r'(if not action_rng_applied then\s+you\.tactical_augment\(100,)\d+(\))'
    changed,count=re.subn(pattern,lambda m:m[1]+str(offset)+m[2],source)
    if count != 1:
        raise ValueError('Unrecognized or ambiguous RNG hook')
    return changed


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--offset-start',type=int,default=6)
    p.add_argument('--offset-count',type=int,default=3)
    args=p.parse_args()
    parent=args.parent.resolve();root=args.output.resolve()
    old=json.loads((parent/'config.json').read_text())
    if not old.get('preflight_passed') or old.get('test_used'):
        raise ValueError('Parent config is not an eligible frozen source')
    parents=[e for e in old['cases'] if e['split']=='train' and e['rng_offset']==0]
    offsets=list(range(args.offset_start,args.offset_start+args.offset_count))
    if len(parents)!=12 or any(o<0 for o in offsets):
        raise ValueError('Expected twelve training families and nonnegative offsets')
    root.mkdir(parents=True,exist_ok=False);(root/'cases').mkdir()
    entries=[]
    for parent_entry in parents:
        origin=Path(parent_entry['case'])
        meta=json.loads((origin/'case.json').read_text())
        if bench.sha(origin/'checkpoint.cs')!=meta['save_sha256'] or bench.sha(origin/'trial.rc')!=meta['rc_sha256']:
            raise ValueError('Changed parent case: '+str(origin))
        for offset in offsets:
            target=root/'cases'/f'{parent_entry["seed"]}-rng-{offset}'
            target.mkdir(parents=True)
            shutil.copy2(origin/'checkpoint.cs',target/'checkpoint.cs')
            (target/'trial.rc').write_text(advance_hook((origin/'trial.rc').read_text(),offset))
            case_meta=dict(meta,rc_sha256=bench.sha(target/'trial.rc'),rng_offset=offset,
                           parent_case=str(origin),parent_rc_sha256=meta['rc_sha256'])
            (target/'case.json').write_text(json.dumps(case_meta,indent=2)+'\n')
            entries.append(dict(parent_entry,id=parent_entry['family']+f'/rng-{offset}',
                                case=str(target),rng_offset=offset,
                                initial_hash=parent_entry['initial_hash']))
    validation=[e for e in old['cases'] if e['split']=='validation']
    if len(validation)!=8:
        raise ValueError('Expected eight frozen validation variants')
    cfg=dict(version=1,engine=old['engine'],engine_sha256=old['engine_sha256'],cache=old['cache'],
             cases=entries+validation,seed_manifest_sha256=old['seed_manifest_sha256'],preflight_passed=False,
             test_used=False,autopickup=False,feature_version=old['feature_version'],
             caveat='Fresh RNG offsets on existing training families; no new seeds.')
    config=root/'config.json';config.write_text(json.dumps(cfg,indent=2)+'\n')
    tasks=[(str(config),entry,i,str(root/'preflight')) for i,entry in enumerate(entries)]
    results=[]
    with ProcessPoolExecutor(max_workers=6,mp_context=mp.get_context('spawn')) as pool:
        for result in pool.map(verify,tasks):
            results.append(result)
    (root/'preflight.json').write_text(json.dumps(results,indent=2)+'\n')
    if not all(x.get('passed') for x in results):
        raise RuntimeError('Fresh preflight failed')
    cfg.update(preflight_passed=True,preflight_sha256=bench.sha(root/'preflight.json'))
    config.write_text(json.dumps(cfg,indent=2)+'\n')
    print(json.dumps(dict(config=str(config),cases=len(entries),offsets=offsets)),flush=True)


if __name__=='__main__':main()
