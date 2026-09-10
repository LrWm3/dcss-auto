"""Small seed-disjoint action pilot; no test cases or existing labels fitted."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path

import bench
from benchmark_transport import digest
from fast_env import derive_fast
from dataset_splits import partition_map, MANIFEST

TRAIN_SEEDS=('83019001','83018001','83017001','83017002','83019003','83018005')
VALIDATION_IDS=('encounter-008','encounter-013','encounter-023','encounter-018')

def verify(task):
    from action_env import ActionEnv, fixed_action
    config, entry, index, output=task
    snapshots=[]; actions=[]
    for repeat in range(2):
        env=ActionEnv(config,Path(output)/f'verify-{entry["split"]}-{index}-{repeat}',entry['split'])
        try:
            env.reset(seed=42,options={'case_index':index})
            if digest(env.state)!=entry['initial_hash']:
                raise RuntimeError('Initial observation divergence')
            hashes=[digest(env.state)]
            for _ in range(16):
                a=fixed_action(env.state,env.action_masks(),'pursue_berserk')
                _,_,terminated,truncated,info=env.step(a)
                hashes.append(digest(env.state))
                actions.append(info)
                if terminated or truncated: break
            snapshots.append(hashes)
        finally:env.close()
    if snapshots[0]!=snapshots[1]:raise RuntimeError('Nondeterministic replay')
    return dict(id=entry['id'],passed=True,steps=len(snapshots[0])-1,
                noops=sum(a['no_op'] for a in actions),hashes=snapshots[0])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    bench.ENGINE=bench.ENGINE.with_name('crawl-tactical-sim')
    training=bench.HERE/'artifacts/character-training-v1'
    index=json.loads((training/'training-index.json').read_text())
    if not index['audited'] or bench.sha(training/'coverage.json')!=index['files']['coverage.json']:
        raise ValueError('Training coverage changed')
    mapping=partition_map(json.loads(MANIFEST.read_text()))
    parents=[]
    for row in json.loads((training/'coverage.json').read_text()):
        if row['seed'] not in TRAIN_SEEDS:continue
        v=next(v for v in row['variants'] if v['recipe']['axis']=='none')
        if mapping[row['seed']]!='train' or not v['replay_verified']:raise ValueError('Invalid training parent')
        parents.append(dict(id=row['id'],case=v['case'],seed=row['seed'],split='train',initial=v['initial']))
    holdout=bench.HERE/'artifacts/goals-character-v2-holdout-v4'
    for row in json.loads((holdout/'coverage.json').read_text()):
        if row['split']!='validation' or row['id'].split('/')[-1] not in VALIDATION_IDS:continue
        if mapping[row['seed']]!='validation' or not row['prefix_verified']:raise ValueError('Invalid validation parent')
        parents.append(dict(id=row['id'],case=str(holdout/row['id']/'rich-case'),
                            seed=row['seed'],split='validation',initial=row['initial']))
    if len(parents)!=10:raise ValueError('Unexpected pilot size')
    entries=[]
    for i,parent in enumerate(parents):
        for offset in (range(3) if parent['split']=='train' else range(2)):
            case=derive_fast(parent['case'],root/'cases'/f'{i:02d}-rng-{offset}')
            source=(case/'trial.rc').read_text();at=source.rfind('\n>')
            hook='''
local action_parent_ready=ready
local action_rng_applied=false
function ready()
  -- Item pickup is outside the ten-action pilot and otherwise consumes a
  -- second automatic turn after some movement commands.
  crawl.setopt("default_autopickup = false")
  if not action_rng_applied then
    you.tactical_augment(100,%d)
    action_rng_applied=true
  end
  action_parent_ready()
end
''' % offset
            (case/'trial.rc').write_text(source[:at]+hook+source[at:]+'\ndefault_autopickup = false\n')
            meta=json.loads((case/'case.json').read_text())
            meta.update(rc_sha256=bench.sha(case/'trial.rc'),action_version=1,rng_offset=offset,
                        split=parent['split'],family_id=parent['id'],training_ready=False)
            (case/'case.json').write_text(json.dumps(meta,indent=2)+'\n')
            entries.append(dict(id=parent['id']+f'/rng-{offset}',case=str(case),seed=parent['seed'],
                family=parent['id'],split=parent['split'],rng_offset=offset,initial_hash=digest(parent['initial'])))
    cfg=dict(version=1,engine=str(bench.ENGINE),engine_sha256=bench.sha(bench.ENGINE),
        cache=str(bench.HERE/'artifacts/simulation-cache-v1'),cases=entries,
        seed_manifest_sha256=bench.sha(MANIFEST),preflight_passed=False,
        test_used=False,autopickup=False,feature_version='rich-v2-hashed8192-history4',
        caveat='Previously studied validation seed; not a pristine final test.')
    config=root/'config.json';config.write_text(json.dumps(cfg,indent=2)+'\n')
    tasks=[]
    for split in ('train','validation'):
        tasks.extend((str(config),e,i,str(root/'preflight'))
                     for i,e in enumerate([e for e in entries if e['split']==split]))
    results=[]
    with ProcessPoolExecutor(max_workers=6,mp_context=multiprocessing.get_context('spawn')) as pool:
        for result in pool.map(verify,tasks):
            results.append(result)
            (root/'preflight.json').write_text(json.dumps(results,indent=2)+'\n')
            print(json.dumps({k:v for k,v in result.items() if k!='hashes'}),flush=True)
    cfg['preflight_passed']=True;cfg['preflight_sha256']=bench.sha(root/'preflight.json')
    config.write_text(json.dumps(cfg,indent=2)+'\n')
    print(str(config),flush=True)

if __name__=='__main__':main()
