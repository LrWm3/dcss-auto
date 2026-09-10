"""Fixed spatial imitation experiment, old-vs-capped sampler training comparison."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('MKL_NUM_THREADS','1')
import numpy as np
import torch
from action_env import ActionEnv, ACTIONS, fixed_action
from audit_action_episodes import audit
from broaden_action_training import report
from dataset_splits import MANIFEST, partition_map
from direction_policy import DirectionPolicy, directional_features, cap_probabilities
from train_action_dagger import sample_weights, stratum
from train_action_imitation import pool_run, save_json
import bench


def rollout(task):
    config,root,split,index,checkpoint=task
    torch.set_num_threads(1);root=Path(root)/f'case-{index:02d}'
    env=ActionEnv(config,root,split)
    model=DirectionPolicy();model.load_state_dict(torch.load(checkpoint,weights_only=True));model.eval()
    try:
        env.reset(seed=16000+index,options={'case_index':index})
        for _ in range(env.max_steps):
            a=model.act(env.state,env.action_masks())
            _,_,done,truncated,_=env.step(a)
            if done or truncated:break
        audit(env.transport.work/'episode.json')
        return json.loads((env.transport.work/'episode.json').read_text())
    finally:env.close()


def extract(result):
    if result['split']!='train':raise ValueError('Only training data permitted')
    worker=Path(result['worker']);audit(worker/'episode.json')
    events=[json.loads(x) for x in (worker/'events.jsonl').read_text().splitlines()]
    rows=[json.loads(x) for x in (worker/'actions.jsonl').read_text().splitlines()]
    state=events[0]['initial_observation'];data=[]
    for event,row in zip(events[1:],rows):
        mask=np.asarray(row['mask'],dtype=bool);teacher=fixed_action(state,mask,'pursue')
        data.append((directional_features(state,mask),mask,teacher,stratum(state,teacher),ACTIONS.index(row['action'])))
        state=event['next_observation']
    return data


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();parent=args.parent.resolve();root=args.output.resolve()
    prior=json.loads((parent/'manifest.json').read_text());config=prior['config']
    if bench.sha(Path(config))!=prior['config_sha256']:raise ValueError('Config changed')
    root.mkdir(parents=True,exist_ok=False);(root/'sources').mkdir()
    sources=['direction_policy.py','train_direction_pilot.py','action_env.py','goal_controllers.py',
             'train_action_dagger.py','broaden_action_training.py','audit_action_episodes.py']
    for name in sources:(root/'sources'/name).write_bytes((bench.HERE/name).read_bytes())
    save_json(root/'manifest.json',dict(parent=str(parent),config=config,config_sha256=bench.sha(Path(config)),
        sources={n:bench.sha(bench.HERE/n) for n in sources},epochs=30,batch=128,lr=.001,
        seed=42,cap_factor=4,validation_model='capped',test_used=False,production_export=False,
        note='Both spatial models start from identical random weights; only sampler differs.'))
    dagger=Path(prior['parent']);original=Path(json.loads((dagger/'manifest.json').read_text())['parent'])
    results=json.loads((original/'demonstrations.json').read_text())
    for folder in (dagger,parent):
        for path in sorted(folder.glob('round-[123].json')):results.extend(json.loads(path.read_text()))
    mapping=partition_map(json.loads(MANIFEST.read_text()))
    if any(mapping[r['seed']]!='train' for r in results):raise ValueError('Seed leakage')
    save_json(root/'dataset-provenance.json',[dict(worker=r['worker'],seed=r['seed'],
        events_sha256=r['events_sha256'],actions_sha256=r['actions_sha256']) for r in results])
    print('Re-encoding audited training states as explicit per-action features',flush=True)
    batches=pool_run(extract,results);rows=[r for batch in batches for r in batch]
    x=np.stack([r[0] for r in rows]);m=np.stack([r[1] for r in rows]);y=np.asarray([r[2] for r in rows])
    groups=np.asarray([r[3] for r in rows]);executed=np.asarray([r[4] for r in rows])
    if len(y)!=8608:raise ValueError('Unexpected dataset size')
    np.savez_compressed(root/'training.npz',features=x,masks=m,actions=y,groups=groups,executed=executed)
    old=sample_weights(groups,y!=executed);capped=cap_probabilities(old)
    save_json(root/'dataset.json',dict(examples=len(y),sha256=bench.sha(root/'training.npz'),
        old_mass=[float(old[groups==g].sum()) for g in range(3)],
        capped_mass=[float(capped[groups==g].sum()) for g in range(3)],
        max_relative_weight=float(capped.max()*len(y))))
    torch.set_num_threads(1);xt=torch.from_numpy(x);mt=torch.from_numpy(m);yt=torch.from_numpy(y).long()
    for name,probability in [('original-sampler',old),('capped',capped)]:
        torch.manual_seed(42);model=DirectionPolicy();optimizer=torch.optim.Adam(model.parameters(),lr=.001)
        rng=np.random.default_rng(42);history=[]
        for epoch in range(30):
            model.train()
            for start in range(0,len(y),128):
                idx=rng.choice(len(y),size=min(128,len(y)-start),p=probability)
                loss=torch.nn.functional.cross_entropy(model(xt[idx],mt[idx]),yt[idx])
                optimizer.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),.5);optimizer.step()
            model.eval()
            with torch.no_grad():pred=torch.cat([model(xt[i:i+256],mt[i:i+256]).argmax(-1) for i in range(0,len(y),256)]).numpy()
            history.append(dict(epoch=epoch+1,accuracy=float((pred==y).mean()),
                by_group={str(g):float((pred[groups==g]==y[groups==g]).mean()) for g in range(3)}))
        torch.save(model.state_dict(),root/(name+'.pt'))
        save_json(root/(name+'-fit.json'),dict(history=history,model_sha256=bench.sha(root/(name+'.pt'))))
        print(name+' '+json.dumps(history[-1]),flush=True)
    summary={}
    for name in ('original-sampler','capped'):
        print('Training replay '+name,flush=True)
        results=pool_run(rollout,[(config,str(root/name/'train'),'train',i,str(root/(name+'.pt'))) for i in range(36)])
        save_json(root/(name+'-evaluation.json'),results);summary[name]=report(results)
        save_json(root/'summary.json',summary);print(json.dumps(summary[name]),flush=True)
    print('Predetermined capped-model validation',flush=True)
    results=pool_run(rollout,[(config,str(root/'capped/validation'),'validation',i,str(root/'capped.pt')) for i in range(8)])
    save_json(root/'validation-evaluation.json',results);summary['validation']=report(results)
    save_json(root/'summary.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
