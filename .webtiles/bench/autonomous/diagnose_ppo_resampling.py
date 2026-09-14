"""Replay the three strongest baseline seeds with new paired action RNGs.

Selection is intentionally outcome-biased: diagnostic, NOT another fresh test.
"""
import train_ppo_pilot
import concurrent.futures
import json
import statistics
import time
from pathlib import Path
import torch
from model import load_model
from general_env import ENGINE,HERE,sha
from ppo_actors import evaluate_episode
from bootstrap_repair import write
import storage


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--suite',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    source=args.suite.resolve();root=args.output.resolve();root.mkdir(parents=True,exist_ok=True)
    storage.configure(root);torch.set_num_threads(1)
    original=json.loads((source/'config.json').read_text())
    baseline=json.loads((source/'baseline-results.json').read_text())
    indices=sorted(range(len(baseline)),key=lambda i:baseline[i]['score'],reverse=True)[:3]
    names=['baseline','run-1-cycle-4','run-2-cycle-4']
    cfg={'selection':'three highest baseline native scores; outcome-biased diagnostic',
         'indices':indices,'seeds':[original['seeds'][i] for i in indices],
         'new_policy_sampling_seeds':[61409001,61409002,61409003,61409004],
         'models':{name:original['models'][name] for name in names},'steps':2000,
         'engine_sha256':sha(ENGINE),'bridge_sha256':sha(HERE/'general_bridge.lua'),
         'training':False,'promotion':False}
    if cfg['engine_sha256']!=original['engine_sha256']:raise ValueError('engine changed')
    for m in cfg['models'].values():
        if sha(Path(m['path']))!=m['sha256']:raise ValueError('model changed')
    if (root/'config.json').exists() and json.loads((root/'config.json').read_text())!=cfg:
        raise ValueError('resume config differs')
    write(root/'config.json',cfg)
    models={name:load_model(cfg['models'][name]['path'])[0] for name in names}
    tasks=[(i,name,rng) for i in indices for rng in cfg['new_policy_sampling_seeds'] for name in names]
    results=[]
    def run(task):
        i,name,rng=task
        result=evaluate_episode(root/name/str(i)/str(rng),models[name],int(original['seeds'][i]),rng)
        return {'index':i,'model':name,'sampling_seed':rng,**result}
    def publish(phase):
        write(root/'latest_status.json',{'phase':phase,'completed':len(results),'total':len(tasks),
              'errors':sum('error' in r for r in results),'updated_at':time.time(),
              'warning':cfg['selection']})
    publish('running')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(run,tasks):
            results.append(result);publish('running')
    report={}
    for i in indices:
        report[str(i)]={name:{'scores':[r.get('score') for r in results if r['index']==i and r['model']==name],
                             'original_score':json.loads((source/f'{name}-results.json').read_text())[i]['score']}
                        for name in names}
    write(root/'results.json',results);write(root/'comparison.json',report);publish('complete')


if __name__=='__main__':main()
