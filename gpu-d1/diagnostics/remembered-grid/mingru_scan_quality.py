"""Saved-checkpoint rollout parity and full-network GPU profile."""
import argparse,hashlib,json
import torch
from symbolic_mingru import MinSymbolicPolicy
from symbolic_fast_quality import PrecisionState
from optimize_symbolic import workload
from run import evaluate,save_json
from runtime import OUT,ROOT


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--profile-only',action='store_true');args=parser.parse_args()
    torch.set_num_threads(1);torch.backends.cudnn.benchmark=True
    path=OUT/'symbolic-mingru/best.pt';ck=torch.load(path,weights_only=False)
    historical=json.loads((ROOT/'results/remembered-grid-symbolic-mingru.json').read_text())
    rows=json.loads((ROOT/'results/symbolic-mingru-scan-quality.json').read_text())['rows'] if args.profile_only else []
    for amp in (() if args.profile_only else (False,True)):
        for split in ('test','long'):
            models={}
            for backend in ('eager','triton'):
                m=MinSymbolicPolicy(backend).cuda();m.load_state_dict(ck['model']);torch.manual_seed(11812)
                models[backend]=evaluate(PrecisionState(m,amp),split)
            ref=models['eager'];opt=models['triton']
            row=dict(amp=amp,split=split,eager=ref['summary'],fused=opt['summary'],episodes=len(ref['rows']),changed_rows=sum(a!=b for a,b in zip(ref['rows'],opt['rows'])),changed_outcomes=sum(any(a[k]!=b[k] for k in ('exit','death','timeout')) for a,b in zip(ref['rows'],opt['rows'])))
            if not amp:row['eager_changed_from_historical']=sum(a!=b for a,b in zip(ref['rows'],historical[split+'_greedy']['rows']))
            rows.append(row);print(row,flush=True)
    m,train=workload(True,True,4096,True,model_factory=lambda:MinSymbolicPolicy('triton'))
    for _ in range(10):train()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in m.parameters())
    with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as p:
        for _ in range(5):train()
    table=p.key_averages().table(sort_by='self_cuda_time_total',row_limit=30)
    (ROOT/'results/symbolic-mingru-scan-profile.txt').write_text('\n'.join(line.rstrip() for line in table.splitlines())+'\n')
    kernels=[e for e in p.events() if str(e.device_type).endswith('CUDA')]
    total=sum(e.device_time_total for e in kernels)
    scan=sum(e.device_time_total for e in kernels if e.name in ('_forward','_backward'))
    profile=dict(profiled_optimizer_steps=5,total_kernel_us=total,scan_kernel_us=scan,scan_kernel_fraction=scan/total if total else None)
    save_json(ROOT/'results/symbolic-mingru-scan-quality.json',dict(rows=rows,profile=profile,checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),checkpoint_update=ck['step']))
    print('profile',profile,flush=True)

if __name__=='__main__':main()
