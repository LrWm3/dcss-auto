"""Live observation equivalence plus fresh six-policy V2 labeling pilot."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from augmentation_dataset import read,verify_result
from augment_encounters import POLICIES
from bench import HERE,sha
from goal_env import GoalEnvironment
from goal_controllers import Controller
from rich_features import features,values
from rich_goals import derive,run,fit,select
from train_encounters import write
from verify_resume import normalized


def original_projection(s):
    return normalized({k:v for k,v in s.items() if k not in
        ('rich_version','player','gear','enemy_details')})


def trial(task):
    e,case,root,policy=task;r=verify_result(run(e,case,root,policy))
    r['split']=e['split'];return r


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args()
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
    corpus=HERE/'artifacts/augmentation-all-v4'
    ids=['development/mining-deeper-v1/collection/encounter-007',
         'development/mining-fresh-training-v1/collection/encounter-019',
         'fresh-evaluation/collection/encounter-021']
    fs={f['id']:f for f in read(corpus/'coverage.json')};checks=[];tasks=[]
    write(root/'manifest.json',dict(families=ids,source_sha256={n:sha(HERE/n) for n in
        ('rich_goal_bridge.lua','rich_features.py','rich_goals.py','check_rich_goals.py')},
        corpus_manifest_sha256=sha(corpus/'manifest.json'),production_export=False))
    snapshots=[]
    for i,ident in enumerate(ids):
        v=fs[ident]['variants'][0];parent=Path(v['case']);case=derive(parent,root/f'case-{i}')
        envs=[GoalEnvironment(root/f'check-{i}') for _ in range(3)]
        try:
            states=[env.reset(c) for env,c in zip(envs,[parent,case,case])]
            assert original_projection(states[0])==original_projection(states[1])
            assert features(states[1])==features(states[2])
            snapshots.append(states[1]);write(root/f'observation-{i}.json',states[1])
            write(root/f'features-{i}.json',features(states[1]))
            controller=Controller('pursue',False);steps=0
            for _ in range(12):
                action=controller(states[0]);states=[env.step(action) for env in envs];steps+=1
                assert original_projection(states[0])==original_projection(states[1])==original_projection(states[2])
                if states[0].get('terminal'):break
                assert features(states[1])==features(states[2])
            checks.append(dict(id=ident,passed=True,prefix_steps=steps,
                feature_count=len(features(snapshots[-1])),workers=[str(env.work) for env in envs]))
        finally:
            for env in envs:env.close()
            write(root/'checks.json',checks)
        entry=dict(id=v['id'],seed=fs[ident]['seed'],split=fs[ident]['split'])
        tasks.extend((entry,case,root/f'trial-{i}-{o.replace(":","-")}',o) for o in POLICIES)
        print(checks[-1],flush=True)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows=[]
        for r in pool.map(trial,tasks):
            rows.append(r);write(root/'results.json',rows)
            print(dict(case=r['case_id'],option=r['option'],outcome=r['outcome']),flush=True)
    usable=[r for r in rows if r['split']=='train' and r.get('evidence_verified') and
            r['outcome'] in ('death','recovered_quiet')]
    model=fit(usable,epochs=20);write(root/'smoke-model.json',model)
    selected=[select(model,s) for s in snapshots]
    summary=dict(verified_prefixes=len(checks),trials=len(rows),
        audited=sum(r.get('evidence_verified',False) for r in rows),smoke_model_choices=selected,
        model_note='20-epoch integration smoke test only; not a benchmarked replacement',
        production_export=False)
    write(root/'summary.json',summary);print(summary,flush=True)
    if any(r['outcome']=='harness_error' for r in rows):raise RuntimeError('Harness errors')


if __name__=='__main__':main()
