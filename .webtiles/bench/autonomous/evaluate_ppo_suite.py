"""Frozen-checkpoint fresh paired evaluation. No learning or promotion."""
import train_ppo_pilot  # Establish the exact pilot observation/action modes.
import argparse
import concurrent.futures
import json
import math
import random
import statistics
import subprocess
import time
from pathlib import Path
import torch
from model import load_model
from general_env import ENGINE,HERE,sha
from ppo_actors import evaluate_episode
from bootstrap_repair import write
from train_ppo_pilot import paired
import storage


def interval(values, alpha=.05, seed=8191):
    rng=random.Random(seed)
    means=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(10000))
    return [means[int(alpha/2*len(means))],means[min(len(means)-1,int((1-alpha/2)*len(means)))]]


def compare(before,after):
    report=paired(before,after)
    if not report['valid']:return report
    d=report['paired_native_deltas']
    strongest=max(range(len(d)),key=lambda i:d[i])
    report.update(native_delta_ci95=interval(d),
                  native_delta_ci9875=interval(d,alpha=.0125),
                  candidate_median_native=statistics.median(r['score'] for r in after),
                  baseline_median_native=statistics.median(r['score'] for r in before),
                  mean_delta_without_largest_gain=statistics.mean(v for i,v in enumerate(d) if i!=strongest)
                      if len(d)>1 else None,
                  warning='paired bootstrap intervals are approximate; 98.75% accounts for four candidate comparisons; no promotion')
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--count',type=int,default=40)
    p.add_argument('--steps',type=int,default=2000)
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--suite-seed',type=int,default=202609131)
    args=p.parse_args()
    if min(args.count,args.steps,args.workers)<1:p.error('counts must be positive')
    source,root=args.source.resolve(),args.output.resolve()
    names={'baseline':source/'initial.pt'}
    for rep in range(2):
        for cycle in (1,3):
            names[f'run-{rep+1}-cycle-{cycle+1}']=source/f'replicate-{rep}'/f'cycle-{cycle:03d}'/'candidate.pt'
    rng=random.Random(args.suite_seed)
    seeds=rng.sample(range(1<<56),args.count)
    seeds=[(0xD<<60)+s for s in seeds]
    policy_seeds=[rng.randrange(1<<32) for _ in seeds]
    original=json.loads((source/'config.json').read_text())
    for key,path in [('engine_sha256',ENGINE),('bridge_sha256',HERE/'general_bridge.lua'),
                     ('features_sha256',HERE/'structured_features.py'),('actors_sha256',HERE/'ppo_actors.py'),
                     ('core_sha256',HERE/'ppo_core.py')]:
        if original[key]!=sha(path):raise ValueError('pilot interface changed: '+key)
    config={'source':str(source),'seeds':[str(s) for s in seeds],'policy_seeds':policy_seeds,
            'models':{k:{'path':str(v),'sha256':sha(v)} for k,v in names.items()},
            'steps':args.steps,'workers':args.workers,'suite_seed':args.suite_seed,
            'mode':'sampled-softmax','automatic_promotion':False,'training':False,
            'engine_sha256':sha(ENGINE),'runner_sha256':sha(Path(__file__)),
            'namespace':'confirmation 0xD; final audit 0xE remains unused'}
    if (root/'config.json').exists():
        if json.loads((root/'config.json').read_text())!=config:raise ValueError('resume config mismatch')
    else:
        # Check persisted JSON manifests/results before publishing this suite.
        cmd=['rg','-l','-F','--glob','*.json']
        for seed in seeds:cmd+=['-e',str(seed)]
        cmd+=[str(HERE/'artifacts')]
        search=subprocess.run(cmd,text=True,capture_output=True)
        if search.returncode!=1:
            raise ValueError('freshness check found a match or failed: '+search.stdout[:2000]+search.stderr[:1000])
        root.mkdir(parents=True,exist_ok=True)
        write(root/'config.json',config)
    storage.configure(root);torch.set_num_threads(1)
    models={name:load_model(path)[0] for name,path in names.items()}
    status={'phase':'evaluation','promoted':False,'mode':'sampled-softmax',
            'seeds':len(seeds),'models':list(names),'total_games':len(seeds)*len(names),'completed_games':0}
    results={name:{} for name in names}
    def publish():
        status['updated_at']=time.time()
        status['completed_games']=sum(len(v) for v in results.values())
        status['errors']=sum('error' in r for v in results.values() for r in v.values())
        status['completed_by_model']={k:len(v) for k,v in results.items()}
        write(root/'latest_status.json',status)
    publish()
    def run(task):
        name,i=task
        path=root/'games'/name/str(i)
        try:
            result=evaluate_episode(path,models[name],seeds[i],policy_seeds[i],args.steps,False)
            if result.get('seed')!=str(seeds[i]):raise ValueError('cached seed mismatch')
            if not result.get('error') and (result.get('policy_sampling_seed')!=policy_seeds[i] or result.get('greedy')):
                raise ValueError('cached policy mode/sampling mismatch')
            return name,i,result
        except Exception as exc:return name,i,{'seed':str(seeds[i]),'error':repr(exc)}
    # Interleave models by seed so partial progress is not an unpaired mean.
    tasks=[(name,i) for i in range(len(seeds)) for name in names]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(run,t) for t in tasks]
        for future in concurrent.futures.as_completed(futures):
            name,i,result=future.result();results[name][i]=result;publish()
    before=[results['baseline'][i] for i in range(len(seeds))]
    comparisons={}
    for name in names:
        values=[results[name][i] for i in range(len(seeds))]
        write(root/f'{name}-results.json',values)
        if name!='baseline':comparisons[name]=compare(before,values)
    write(root/'comparisons.json',comparisons)
    status.update(phase='complete' if not status['errors'] else 'complete_with_errors',comparisons=comparisons)
    publish()


if __name__=='__main__':main()
