"""Repair an existing V6 bootstrap in a separate artifact directory."""
import os
os.environ['DCSS_REPRESENTATION']='spatial-v6'
import argparse
from pathlib import Path
import torch
import storage
from bootstrap_repair import read_training, repair, write, VALIDATION_SEEDS

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source-run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--rounds',type=int,default=3)
    p.add_argument('--initial-checkpoint',type=Path)
    p.add_argument('--seed-offset',type=int,default=0)
    p.add_argument('--validation-seed-offset',type=int,default=0)
    args=p.parse_args();torch.set_num_threads(1)
    args.output.mkdir(parents=True,exist_ok=True);storage.configure(args.output)
    if not (args.output/'status.json').exists():
        write(args.output/'status.json',{'phase':'loading_training_replay','source':str(args.source_run)})
    rows=read_training(args.source_run/'replay')
    initial=args.initial_checkpoint or args.source_run/'champions/V0.pt'
    validation=[str(int(s)+args.validation_seed_offset) for s in VALIDATION_SEEDS]
    print(repair(args.output,initial,rows,args.rounds,validation,args.seed_offset),flush=True)

if __name__=='__main__':main()
