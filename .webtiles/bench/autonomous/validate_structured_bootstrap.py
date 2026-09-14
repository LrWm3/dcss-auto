"""Run the bootstrap navigation gate without fitting or promoting a policy."""
import os
os.environ['DCSS_REPRESENTATION']='spatial-v6'
import argparse
from pathlib import Path
import torch
import storage
from bootstrap_repair import VALIDATION_SEEDS,play_batch,navigation_gate,write

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);args=p.parse_args()
    torch.set_num_threads(1);args.output.mkdir(parents=True,exist_ok=True);storage.configure(args.output)
    write(args.output/'status.json',{'phase':'validating','model':str(args.model)})
    results=play_batch(args.output,args.model,VALIDATION_SEEDS,False)
    gate=navigation_gate(results);write(args.output/'gate.json',gate)
    write(args.output/'status.json',{'phase':'complete','gate':gate})
    print(gate)

if __name__=='__main__':main()
