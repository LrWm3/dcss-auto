"""Re-evaluate an existing health-feature checkpoint without retraining."""
import os
os.environ['DCSS_REPRESENTATION']='spatial-v6'
os.environ['DCSS_HEALTH_FEATURES']='1'
import argparse
from pathlib import Path
import torch
import storage
from rollout_liveness import rollout_check

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();torch.set_num_threads(1)
    args.output.mkdir(parents=True,exist_ok=True);storage.configure(args.output)
    print(rollout_check(args.model,args.source,args.output))
