"""Double training seed coverage, then two fixed learner-label correction rounds."""
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np
import torch
from sb3_contrib import MaskablePPO
import bench
from action_env import ACTIONS, fixed_action
from benchmark_transport import digest
from dataset_splits import MANIFEST, partition_map
from fast_env import derive_fast
from prepare_action_pilot import verify
from train_action_imitation import pool_run, save_json, train_case
from train_action_ppo import evaluate
from train_action_dagger import collect, fit, load_labels, stratum


def combat_metrics(result):
    events=[json.loads(x) for x in (Path(result['worker'])/'events.jsonl').read_text().splitlines()]
    actions=[json.loads(x) for x in (Path(result['worker'])/'actions.jsonl').read_text().splitlines()]
    state=events[0]['initial_observation']; counts=Counter(decisions=len(actions))
    for event,row in zip(events[1:],actions):
        es=state.get('monsters',{}); es=list(es.values()) if isinstance(es,dict) else es
        adjacent=any(max(abs(e['x']),abs(e['y']))<=1 for e in es)
        teacher=fixed_action(state,np.asarray(row['mask'],dtype=bool),'pursue')
        counts['adjacent_enemy_decisions']+=adjacent
        counts['adjacent_enemy_waits']+=adjacent and row['action']=='wait'
        counts['wait_when_teacher_would_act']+=row['action']=='wait' and teacher!=ACTIONS.index('wait')
        state=event['next_observation']
    return dict(counts)


def report(rows):
    metrics=Counter()
    for r in rows:
        if r['outcome']=='harness_error':continue
        metrics.update(combat_metrics(r))
    return dict(outcomes=dict(Counter(r['outcome'] for r in rows)),combat=dict(metrics))


def prepare(root,previous):
    original=Path(previous['config']);cfg=json.loads(original.read_text())
    if bench.sha(original)!=previous['config_sha256']:raise ValueError('Changed parent config')
    cfg['cases']=list(cfg['cases']); cfg['preflight_passed']=False
    bench.ENGINE=Path(cfg['engine'])
    mapping=partition_map(json.loads(MANIFEST.read_text()))
    training=bench.HERE/'artifacts/character-training-v1'
    index=json.loads((training/'training-index.json').read_text())
    if not index['audited'] or bench.sha(training/'coverage.json')!=index['files']['coverage.json']:
        raise ValueError('Unaudited training coverage')
    old_seeds={e['seed'] for e in cfg['cases'] if e['split']=='train'}
    new=[]
    for row in json.loads((training/'coverage.json').read_text()):
        if row['seed'] in old_seeds:continue
        if mapping[row['seed']]!='train':raise ValueError('Nontraining parent')
        v=next(v for v in row['variants'] if v['recipe']['axis']=='none')
        if not v['replay_verified']:raise ValueError('Unverified parent')
        for offset in range(3):
            case=derive_fast(v['case'],root/'cases'/f'{row["seed"]}-rng-{offset}')
            source=(case/'trial.rc').read_text();at=source.rfind('\n>')
            if at<0:raise ValueError('Missing Lua section')
            hook='''
local action_parent_ready=ready
local action_rng_applied=false
function ready()
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
                        split='train',family_id=row['id'],training_ready=False)
            save_json(case/'case.json',meta)
            new.append(dict(id=row['id']+f'/rng-{offset}',case=str(case),seed=row['seed'],
                family=row['id'],split='train',rng_offset=offset,initial_hash=digest(v['initial'])))
    if len(new)!=18:raise ValueError('Expected six additional seeds, 18 variants')
    cfg['cases'].extend(new);cfg['parent_config']=str(original)
    path=root/'config.json';save_json(path,cfg)
    train=[e for e in cfg['cases'] if e['split']=='train']
    tasks=[(str(path),e,i,str(root/'preflight')) for i,e in enumerate(train) if e in new]
    results=pool_run(verify,tasks);save_json(root/'preflight.json',results)
    cfg.update(preflight_passed=True,preflight_sha256=bench.sha(root/'preflight.json'),
               preflight_scope='18 new variants; original variants retain parent preflight')
    save_json(path,cfg)
    return path,cfg


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();parent=args.parent.resolve();root=args.output.resolve()
    previous=json.loads((parent/'manifest.json').read_text())
    expected=json.loads((parent/'round-3-fit.json').read_text())['model_sha256']
    if bench.sha(parent/'round-3.zip')!=expected:raise ValueError('Changed initialization')
    root.mkdir(parents=True,exist_ok=False);(root/'sources').mkdir()
    sources=['broaden_action_training.py','train_action_dagger.py','action_env.py',
             'train_action_imitation.py','train_action_ppo.py','prepare_action_pilot.py',
             'rich_features.py','goal_controllers.py','audit_dagger_labels.py']
    for name in sources:(root/'sources'/name).write_bytes((bench.HERE/name).read_bytes())
    manifest=dict(parent=str(parent),initialization_sha256=expected,rounds=2,epochs_per_round=10,
        additional_seeds=6,total_train_seeds=12,offsets=[0,1,2],seed=42,
        sources={n:bench.sha(bench.HERE/n) for n in sources},test_used=False,
        validation_selection=False,production_export=False)
    save_json(root/'manifest.json',manifest)
    print('Preflighting 18 new training variants',flush=True)
    config,cfg=prepare(root,previous);manifest.update(config=str(config),config_sha256=bench.sha(config))
    save_json(root/'manifest.json',manifest)
    arrays=[];initial=Path(previous['parent'])
    for r in json.loads((initial/'demonstrations.json').read_text()):
        if r['split']!='train' or bench.sha(Path(r['demonstrations']))!=r['demonstrations_sha256']:
            raise ValueError('Changed original training data')
        with np.load(r['demonstrations']) as data:a={k:data[k] for k in data.files}
        events=[json.loads(x) for x in (Path(r['worker'])/'events.jsonl').read_text().splitlines()]
        states=[events[0]['initial_observation']]+[e['next_observation'] for e in events[1:-1]]
        a['groups']=np.asarray([stratum(s,int(t)) for s,t in zip(states,a['actions'])])
        a['executed']=a['actions'].copy();arrays.append(a)
    for path in sorted(parent.glob('round-[123].json')):
        arrays.extend(load_labels(r) for r in json.loads(path.read_text()))
    torch.set_num_threads(1);torch.manual_seed(42)
    model=MaskablePPO.load(parent/'round-3.zip',device='cpu');checkpoint=parent/'round-3.zip'
    for round_id in (1,2):
        print(f'Broader learner-state collection round {round_id}',flush=True)
        rows=pool_run(collect,[(str(config),str(root/f'round-{round_id}'),i,str(checkpoint)) for i in range(36)])
        save_json(root/f'round-{round_id}.json',rows)
        arrays.extend(load_labels(r) for r in rows)
        stats=fit(model,arrays,10,50+round_id)
        checkpoint=root/f'round-{round_id}.zip';model.save(checkpoint)
        stats.update(model_sha256=bench.sha(checkpoint),collection=report(rows),
                     disagreements=sum(r['disagreements'] for r in rows))
        save_json(root/f'round-{round_id}-fit.json',stats);print(json.dumps(stats),flush=True)
    # Only the predetermined final checkpoint gets validation; no interim tuning.
    train=pool_run(train_case,[(str(config),str(root/'final/train'),i,str(checkpoint)) for i in range(36)])
    save_json(root/'train-evaluation.json',train)
    teacher=pool_run(train_case,[(str(config),str(root/'teacher/train'),i,None) for i in range(36)])
    save_json(root/'teacher-evaluation.json',teacher)
    val=pool_run(evaluate,[(str(config),str(root/'final/validation'),'ppo',i,str(checkpoint)) for i in range(8)])
    save_json(root/'validation-evaluation.json',val)
    summary=dict(train=report(train),teacher=report(teacher),validation=report(val))
    save_json(root/'summary.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
