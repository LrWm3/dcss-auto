"""Resume frozen DAgger evaluation, reusing only audited completed episodes."""
import argparse
from collections import Counter
import json
from pathlib import Path
import bench
from audit_action_episodes import audit
from train_action_imitation import pool_run, save_json, train_case
from train_action_ppo import evaluate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path)
    args=p.parse_args();root=args.root.resolve()
    manifest=json.loads((root/'manifest.json').read_text());config=manifest['config']
    if bench.sha(Path(config))!=manifest['config_sha256']:raise ValueError('Config changed')
    cases=json.loads(Path(config).read_text())['cases']
    provenance=dict(checkpoints={name:bench.sha(root/(name+'.zip')) for name in ('balanced','round-3')},
        sources={name:bench.sha(bench.HERE/name) for name in ('action_env.py','evaluate_action_dagger.py')},
        note='Bounded PTY exit-status retry only; gameplay, models and budgets unchanged')
    path=root/'resumed-evaluation-manifest.json'
    if path.exists() and json.loads(path.read_text())!=provenance:raise ValueError('Resume provenance changed')
    save_json(path,provenance)
    results={}
    for name in ('balanced','round-3'):
        checkpoint=str(root/(name+'.zip'));splits={}
        for split in ('train','validation'):
            completed=[];tasks=[]
            for i in range(sum(e['split']==split for e in cases)):
                if split=='train':
                    work=root/name/'train-evaluation'
                    paths=list((work/f'case-{i:02d}').glob('worker-*/episode.json'))
                    valid=[json.loads(p.read_text()) for p in paths
                           if json.loads(p.read_text())['outcome'] in ('death','recovered_quiet','budget_truncated')]
                    for r in valid:audit(Path(r['worker'])/'episode.json')
                    if len(valid)>1:raise ValueError('Ambiguous duplicate completed trial')
                    if valid:completed.extend(valid)
                    else:tasks.append((config,str(work),i,checkpoint))
                else:
                    work=root/name/'validation'
                    path=work/'ppo'/f'case-{i:02d}'/'evaluation.json'
                    r=json.loads(path.read_text()) if path.exists() else None
                    if r and r['outcome'] in ('death','recovered_quiet','budget_truncated'):
                        audit(Path(r['worker'])/'episode.json');completed.append(r)
                    else:tasks.append((config,str(work),'ppo',i,checkpoint))
            print(f'{name} {split}: reuse {len(completed)}, run {len(tasks)}',flush=True)
            completed.extend(pool_run(train_case if split=='train' else evaluate,tasks) if tasks else [])
            splits[split]=completed
        save_json(root/(name+'-evaluation.json'),splits)
        results[name]={s:dict(Counter(r['outcome'] for r in rows)) for s,rows in splits.items()}
        save_json(root/'summary.json',results);print(json.dumps(results[name]),flush=True)


if __name__=='__main__':main()
