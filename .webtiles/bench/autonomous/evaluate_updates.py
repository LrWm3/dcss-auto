"""Paired fresh-game validation of checkpoint updates with floor-aware budgets."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import torch
from collect import run_episode
import storage


def trial(task):
    root, label, checkpoint, seed, per_floor, total = task
    root=Path(root)
    torch.set_num_threads(1)
    storage.configure(root)
    try:
        return run_episode(root/label/seed, seed, per_floor, model_path=checkpoint,
                           epsilon=0, policy_version=label, snapshot=False, total_steps=total)
    except Exception as exc:
        return {"seed":seed,"policy_version":label,"error":repr(exc)}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--models",nargs="+",required=True,help="LABEL=CHECKPOINT")
    p.add_argument("--seeds",nargs="+",default=[str(910000000000+i) for i in range(5)])
    p.add_argument("--decisions-per-floor",type=int,default=2000)
    p.add_argument("--total-steps",type=int,default=100000)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    tasks=[]
    for spec in args.models:
        label,checkpoint=spec.split("=",1)
        if not label.replace("-","").replace("_","").isalnum():
            raise ValueError("invalid model label")
        tasks.extend((str(args.output.resolve()),label,str(Path(checkpoint).resolve()),s,
                      args.decisions_per_floor,args.total_steps) for s in args.seeds)
    (args.output/"config.json").write_text(json.dumps({"models":args.models,"seeds":args.seeds,
        "decisions_per_floor":args.decisions_per_floor,"total_steps":args.total_steps},indent=2)+"\n")
    results=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(trial,t) for t in tasks]):
            result=future.result()
            results.append(result)
            tmp=args.output/"results.json.tmp"
            tmp.write_text(json.dumps(results,indent=2)+"\n")
            tmp.replace(args.output/"results.json")
            print(json.dumps(result),flush=True)
