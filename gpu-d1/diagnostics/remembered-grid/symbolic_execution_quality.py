"""Saved-checkpoint behavior for compilation and graph execution separately."""
import hashlib,time
import torch
from symbolic_execution import PolicyExecution,StaticInference
from benchmark_symbolic_execution import ARMS
from optimize_symbolic import load
from runtime import ROOT,OUT
from run import evaluate,save_json


def main():
    torch.set_num_threads(1);torch.backends.cudnn.benchmark=True
    rows=[];path=ROOT/'results/symbolic-execution-quality.json'
    for amp in (False,True):
        for split in ('test','long'):
            reference=None
            for name,compiled,graphed in ARMS:
                print('starting',name,amp,split,flush=True)
                m=load(True).configure_encoder(True,True);execution=PolicyExecution(m,compiled)
                policy=StaticInference(execution,amp,graphed);torch.manual_seed(11812)
                result=evaluate(policy,split)
                if reference is None:reference=result
                row=dict(arm=name,amp=amp,split=split,summary=result['summary'],episodes=len(result['rows']),seconds_including_setup=result['seconds'],changed_rows=sum(a!=b for a,b in zip(reference['rows'],result['rows'])),changed_outcomes=sum(any(a[k]!=b[k] for k in ('exit','death','timeout')) for a,b in zip(reference['rows'],result['rows'])))
                rows.append(row);print(row,flush=True)
                save_json(path,dict(rows=rows,checkpoint_sha256=hashlib.sha256((OUT/'symbolic-gru/best.pt').read_bytes()).hexdigest(),scope='Existing optimized GRU checkpoint, synthetic32x32 main/long held-out maps, matched precision greedy rollouts, no retraining. Graph reset at episode-batch boundaries.'))
                del policy,execution,m
    print('finished',flush=True)

if __name__=='__main__':main()
