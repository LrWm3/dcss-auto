"""Existing-checkpoint rollout comparison and before/after GPU profiles."""
import hashlib
import torch
from benchmark_symbolic_encoder import ARMS
from symbolic_fast_quality import PrecisionState
from optimize_symbolic import load,workload
from symbolic_fast import FastSymbolicPolicy
from runtime import ROOT,OUT
from run import evaluate,save_json


def main():
    torch.set_num_threads(1);torch.backends.cudnn.benchmark=True
    rows=[];profiles=[]
    for amp in (False,True):
        for split in ('test','long'):
            reference=None
            for name,skip,layout in ARMS:
                model=load(True).configure_encoder(skip,layout);torch.manual_seed(11812)
                result=evaluate(PrecisionState(model,amp),split)
                if reference is None:reference=result
                row=dict(arm=name,amp=amp,split=split,summary=result['summary'],episodes=len(result['rows']),changed_rows=sum(a!=b for a,b in zip(reference['rows'],result['rows'])),changed_outcomes=sum(any(a[k]!=b[k] for k in ('exit','death','timeout')) for a,b in zip(reference['rows'],result['rows'])))
                rows.append(row);print(row,flush=True)
    for name,skip,layout in [ARMS[0],ARMS[-1]]:
        torch.manual_seed(97)
        model,train=workload(True,True,4096,True,model_factory=lambda:FastSymbolicPolicy(True,skip,layout))
        for _ in range(10):train()
        assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())
        with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as prof:
            for _ in range(5):train()
        table=prof.key_averages().table(sort_by='self_cuda_time_total',row_limit=30)
        (ROOT/('results/symbolic-encoder-profile-'+name+'.txt')).write_text('\n'.join(line.rstrip() for line in table.splitlines())+'\n')
        kernels=[e for e in prof.events() if str(e.device_type).endswith('CUDA')]
        profiles.append(dict(arm=name,optimizer_steps=5,total_kernel_us=sum(e.device_time_total for e in kernels),layout_conversion_kernel_us=sum(e.device_time_total for e in kernels if 'nchwToNhwc' in e.name or 'nhwcToNchw' in e.name or 'NhwcToNchw' in e.name),adaptive_pool_self_cuda_us=sum(e.self_device_time_total for e in prof.key_averages() if e.key.startswith('aten::_adaptive_avg_pool2d'))))
    save_json(ROOT/'results/symbolic-encoder-quality.json',dict(rows=rows,profiles=profiles,checkpoint_sha256=hashlib.sha256((OUT/'symbolic-gru/best.pt').read_bytes()).hexdigest(),scope='Same saved GRU checkpoint; all four arms on same main/long splits; matched precision, greedy evaluation. No retraining.'))
    print('profiles',profiles,flush=True)

if __name__=='__main__':main()
