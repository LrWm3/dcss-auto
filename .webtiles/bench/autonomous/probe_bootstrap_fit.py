"""Training-only controlled fit probe; no evaluation seeds used for fitting."""
import os
os.environ['DCSS_REPRESENTATION']='spatial-v6'
import argparse
from pathlib import Path
from collections import Counter
import torch
from bootstrap_repair import read_training,fit,write,dropout_recent_actions
from model import load_model,save_model,ActionValueModel,tensor_for_actions
import storage

def accuracy(model,rows):
    result={}
    for mask in (False,True):
        counts=Counter();correct=0
        for r in rows:
            s=r['observation'];a=s['actions'];x=tensor_for_actions(s,a)
            if mask:x=dropout_recent_actions(x)
            with torch.no_grad():i=int(model(x).argmax())
            target=r['teacher_action_index'];correct+=int(i==target)
            counts[a[target]['kind']+' -> '+a[i]['kind']]+=1
        result['masked' if mask else 'original']={'accuracy':correct/max(1,len(rows)),'confusion':dict(counts)}
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    torch.set_num_threads(1);args.output.mkdir(parents=True,exist_ok=True);storage.configure(args.output)
    demos=read_training(args.root/'demonstrations',limit=256)
    corrections=read_training(args.root/'round-02/corrections',limit=256)
    rows=demos+corrections;report={}
    for variant in ('warm','fresh'):
        torch.manual_seed(9)
        model=(load_model(args.root/'round-02/model.pt')[0] if variant=='warm' else ActionValueModel())
        report[variant]={'before':accuracy(model,rows)}
        write(args.output/'status.json',{'phase':'fitting','variant':variant})
        report[variant]['training']=fit(model,rows,9,epochs=12,learning_rate=3e-4,limit=512)
        report[variant]['after']=accuracy(model,rows)
        save_model(args.output/(variant+'.pt'),model,{'fit_probe':report[variant]})
        write(args.output/'report.json',report)
    write(args.output/'status.json',{'phase':'complete'})
    print(report)

if __name__=='__main__':main()
