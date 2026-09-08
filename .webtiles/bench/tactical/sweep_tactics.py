"""Paired fixed-tactic trials on verified checkpoints; no policy training."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import json
from pathlib import Path
import random

from bench import ENGINE,sha,HERE
from train_encounters import load_cases,run_episode,validate,write
from tactical_options import Tactic,POLICIES


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('config',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();cfg=json.loads(a.config.read_text());validate(cfg)
    (_,cases),index_path=load_cases(cfg)
    policies=cfg.get('policies',list(POLICIES))
    if not policies or len(set(policies))!=len(policies) or any(p not in POLICIES for p in policies):
        raise ValueError('Invalid policies')
    jobs=cfg.get('jobs',3)
    if type(jobs)is not int or jobs<1:raise ValueError('Invalid jobs')
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
    write(root/'config.json',cfg)
    write(root/'manifest.json',dict(engine_sha256=sha(ENGINE),dataset_sha256=sha(index_path),
        files={n:sha(HERE/n) for n in ('sweep_tactics.py','tactical_options.py','train_encounters.py')},
        scope='Fixed-tactic in-sample selection; repeats are not independent encounters.'))
    schedule=[(e,p,r) for e in cases for p in policies for r in range(cfg['eval_repeats'])]
    def trial(args):
        i,(entry,policy,repeat)=args;work=root/f'trial-{i:03d}';work.mkdir()
        result=run_episode(entry,work,policy,{},random.Random(0),cfg,controller=Tactic(policy))
        result.update(repeat=repeat,trial=i)
        write(work/'result.json',result)
        print(json.dumps({k:result.get(k) for k in ('trial','policy','outcome','decisions','handoff','error')}),flush=True)
        return result
    with ThreadPoolExecutor(max_workers=jobs) as pool:results=list(pool.map(trial,enumerate(schedule)))
    write(root/'results.json',results)
    summary={p:dict(outcomes=dict(Counter(r['outcome'] for r in results if r['policy']==p)),
        handoffs=dict(Counter(r['handoff']['outcome'] for r in results if r['policy']==p and 'handoff'in r)),
        recovered_after_handoff=sum(r.get('handoff',{}).get('recovered_at_end',False)
                                    for r in results if r['policy']==p)) for p in policies}
    write(root/'summary.json',summary);print(json.dumps(summary),flush=True)
    return int(any(r['outcome']=='harness_error' or r.get('handoff',{}).get('outcome')=='harness_error' for r in results))


if __name__=='__main__':raise SystemExit(main())
