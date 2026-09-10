"""Run paired never/near berserk controls on a prepared config."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
import multiprocessing as mp
from pathlib import Path

from learn_berserk_timing import trial
from train_action_imitation import save_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    cfg=json.loads(args.config.read_text());count=sum(e['split']=='train' for e in cfg['cases'])
    tasks=[(str(args.config.resolve()),str(root),'train',i,rule)
           for rule in ('never','near') for i in range(count)]
    results=[]
    with ProcessPoolExecutor(max_workers=6,mp_context=mp.get_context('spawn')) as pool:
        for future in as_completed([pool.submit(trial,t) for t in tasks]):
            result=future.result();results.append(result)
            save_json(root/'trials.json',results)
            if result['outcome']=='harness_error':print(json.dumps(result),flush=True)
    if len(results)!=len(tasks) or any(x['outcome']=='harness_error' for x in results):
        raise RuntimeError('Incomplete paired matrix')
    save_json(root/'summary.json',dict(trials=len(results),outcomes=dict(Counter(x['outcome'] for x in results)),
        policies=dict(Counter(x['rule'] for x in results))))
    print(json.dumps(json.loads((root/'summary.json').read_text())),flush=True)


if __name__=='__main__':main()
