"""One bounded collection -> audited labels -> directional fit -> evaluation cycle."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('MKL_NUM_THREADS','1')
import numpy as np
import torch
import bench
from direction_policy import DirectionPolicy,cap_probabilities
from train_action_dagger import sample_weights
from train_direction_pilot import rollout,extract
from train_action_imitation import pool_run,save_json,train_case
from broaden_action_training import report
from prepare_action_pilot import verify
from dataset_splits import MANIFEST,partition_map


def advance_hook(source,offset):
    pattern=r'(if not action_rng_applied then\s+you\.tactical_augment\(100,)\d+(\))'
    changed,count=re.subn(pattern,lambda m:m[1]+str(offset)+m[2],source)
    if count!=1:raise ValueError('Unrecognized or ambiguous RNG hook')
    return changed


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--rng-start',type=int,default=3)
    args=p.parse_args();parent=args.parent.resolve();root=args.output.resolve()
    prior=json.loads((parent/'manifest.json').read_text());oldconfig=Path(prior['config'])
    if bench.sha(oldconfig)!=prior['config_sha256']:raise ValueError('Changed parent config')
    checkpoint=parent/'capped.pt';dataset=parent/'training.npz'
    if bench.sha(checkpoint)!=json.loads((parent/'capped-fit.json').read_text())['model_sha256']:
        raise ValueError('Changed model')
    if bench.sha(dataset)!=json.loads((parent/'dataset.json').read_text())['sha256']:
        raise ValueError('Changed dataset')
    cfg=json.loads(oldconfig.read_text());oldtrain=[e for e in cfg['cases'] if e['split']=='train']
    parents=[e for e in oldtrain if e['rng_offset']==0]
    mapping=partition_map(json.loads(MANIFEST.read_text()))
    if not parents or any(mapping[e['seed']]!='train' for e in oldtrain):raise ValueError('Invalid training seeds')
    offsets=list(range(args.rng_start,args.rng_start+3))
    if args.rng_start<0 or any(e['rng_offset'] in offsets for e in oldtrain):
        raise ValueError('Offsets must be new to this training config')
    root.mkdir(parents=True,exist_ok=False);(root/'sources').mkdir()
    sources=['run_direction_cycle.py','direction_policy.py','train_direction_pilot.py',
             'train_action_dagger.py','action_env.py','goal_controllers.py','prepare_action_pilot.py',
             'broaden_action_training.py','audit_action_episodes.py']
    for name in sources:(root/'sources'/name).write_bytes((bench.HERE/name).read_bytes())
    manifest=dict(parent=str(parent),parent_config_sha256=bench.sha(oldconfig),
        initial_model_sha256=bench.sha(checkpoint),parent_dataset_sha256=bench.sha(dataset),
        offsets=offsets,epochs=10,batch=128,lr=.001,seed=43,cap_factor=4,
        sources={n:bench.sha(bench.HERE/n) for n in sources},test_used=False,
        validation_selection=False,production_export=False)
    save_json(root/'manifest.json',manifest)
    new=[]
    for e in parents:
        origin=Path(e['case']);meta=json.loads((origin/'case.json').read_text())
        if bench.sha(origin/'checkpoint.cs')!=meta['save_sha256'] or bench.sha(origin/'trial.rc')!=meta['rc_sha256']:
            raise ValueError('Changed parent case')
        for offset in offsets:
            target=root/'cases'/f'{e["seed"]}-rng-{offset}';target.mkdir(parents=True)
            shutil.copy2(origin/'checkpoint.cs',target/'checkpoint.cs')
            (target/'trial.rc').write_text(advance_hook((origin/'trial.rc').read_text(),offset))
            save_json(target/'case.json',dict(meta,rc_sha256=bench.sha(target/'trial.rc'),
                rng_offset=offset,parent_case=str(origin),parent_rc_sha256=meta['rc_sha256']))
            new.append(dict(e,id=e['family']+f'/rng-{offset}',case=str(target),rng_offset=offset))
    cfg.update(cases=cfg['cases']+new,preflight_passed=False,parent_config=str(oldconfig))
    config=root/'config.json';save_json(config,cfg)
    print(f'Preflight: {len(new)} new variants',flush=True)
    checks=pool_run(verify,[(str(config),e,len(oldtrain)+i,str(root/'preflight')) for i,e in enumerate(new)])
    save_json(root/'preflight.json',checks)
    cfg.update(preflight_passed=True,preflight_sha256=bench.sha(root/'preflight.json'),
               preflight_scope='New offsets only; existing cases retain parent preflight')
    save_json(config,cfg);manifest.update(config=str(config),config_sha256=bench.sha(config))
    save_json(root/'manifest.json',manifest)
    print('Collection: starting learner controls fresh training offsets',flush=True)
    collection=pool_run(rollout,[(str(config),str(root/'collection'),'train',len(oldtrain)+i,str(checkpoint)) for i in range(len(new))])
    save_json(root/'collection.json',collection);print(json.dumps(report(collection)),flush=True)
    batches=pool_run(extract,collection);rows=[r for batch in batches for r in batch]
    fresh=dict(features=np.stack([r[0] for r in rows]),masks=np.stack([r[1] for r in rows]),
        actions=np.asarray([r[2] for r in rows]),groups=np.asarray([r[3] for r in rows]),executed=np.asarray([r[4] for r in rows]))
    np.savez_compressed(root/'new-labels.npz',**fresh)
    with np.load(dataset) as previous:data={k:np.concatenate([previous[k],fresh[k]]) for k in fresh}
    np.savez_compressed(root/'training.npz',**data)
    save_json(root/'dataset.json',dict(sha256=bench.sha(root/'training.npz'),
        new_labels_sha256=bench.sha(root/'new-labels.npz'),examples=len(data['actions']),
        new_examples=len(rows),disagreements=int((fresh['actions']!=fresh['executed']).sum()),
        parent=str(dataset),parent_sha256=bench.sha(dataset)))
    x=torch.from_numpy(data['features']);m=torch.from_numpy(data['masks']);y=torch.from_numpy(data['actions']).long()
    if not bool(m.gather(1,y[:,None]).all()):raise ValueError('Illegal teacher label')
    probability=cap_probabilities(sample_weights(data['groups'],data['actions']!=data['executed']))
    torch.set_num_threads(1);torch.manual_seed(43)
    model=DirectionPolicy();model.load_state_dict(torch.load(checkpoint,weights_only=True))
    optimizer=torch.optim.Adam(model.parameters(),lr=.001);rng=np.random.default_rng(43);history=[]
    for epoch in range(10):
        model.train()
        for start in range(0,len(y),128):
            idx=rng.choice(len(y),size=min(128,len(y)-start),p=probability)
            loss=torch.nn.functional.cross_entropy(model(x[idx],m[idx]),y[idx])
            optimizer.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),.5);optimizer.step()
        model.eval()
        with torch.no_grad():pred=torch.cat([model(x[i:i+256],m[i:i+256]).argmax(-1) for i in range(0,len(y),256)])
        history.append(dict(epoch=epoch+1,accuracy=float((pred==y).float().mean())))
    torch.save(model.state_dict(),root/'capped.pt')
    save_json(root/'capped-fit.json',dict(history=history,model_sha256=bench.sha(root/'capped.pt')))
    print('Fixed final model evaluation',flush=True)
    final=pool_run(rollout,[(str(config),str(root/'final/train'),'train',i,str(root/'capped.pt')) for i in range(len(oldtrain)+len(new))])
    save_json(root/'train-evaluation.json',final)
    teacher=pool_run(train_case,[(str(config),str(root/'teacher/train'),len(oldtrain)+i,None) for i in range(len(new))])
    save_json(root/'teacher-evaluation.json',teacher)
    val=pool_run(rollout,[(str(config),str(root/'final/validation'),'validation',i,str(root/'capped.pt'))
                        for i in range(sum(e['split']=='validation' for e in cfg['cases']))])
    save_json(root/'validation-evaluation.json',val)
    summary=dict(collection=report(collection),original_train=report(final[:len(oldtrain)]),
        new_train=report(final[len(oldtrain):]),teacher_new=report(teacher),validation=report(val))
    save_json(root/'summary.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
