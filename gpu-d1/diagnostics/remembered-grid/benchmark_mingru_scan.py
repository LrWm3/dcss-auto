"""Matched recurrent-only and whole-network benchmark for fused minGRU."""
import argparse,json,os,statistics,subprocess,time
import torch
from symbolic_fast import FastSymbolicPolicy
from symbolic_mingru import MinSymbolicPolicy
from optimize_symbolic import workload,inputs
from runtime import ROOT
from run import save_json

FACTORIES=[('gru',FastSymbolicPolicy),('mingru_eager',MinSymbolicPolicy),('mingru_fused',lambda:MinSymbolicPolicy('triton'))]


def timed(fn,reps=40):
    for _ in range(10):fn()
    samples=[]
    for _ in range(3):
        torch.cuda.synchronize();start=time.perf_counter()
        for _ in range(reps):fn()
        torch.cuda.synchronize();samples.append((time.perf_counter()-start)/reps*1000)
    return dict(ms=statistics.median(samples),samples_ms=samples)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--reverse',action='store_true');args=parser.parse_args()
    factories=list(reversed(FACTORIES)) if args.reverse else FACTORIES
    torch.set_num_threads(1);torch.backends.cudnn.benchmark=True
    other=[x for x in subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True).strip().splitlines() if x.split(',')[0].strip()!=str(os.getpid())]
    assert not other,other
    micro=[];full=[]
    for batch,t,amp in [(16,16,False),(256,16,True),(16,128,True)]:
        for name,factory in factories:
            torch.manual_seed(97);m=factory().cuda()
            x=torch.randn(batch,t,194,device='cuda',requires_grad=True);h=torch.rand(batch,128,device='cuda',requires_grad=True)
            weight=torch.randn(batch,t,128,device='cuda')
            @torch.no_grad()
            def forward():
                with torch.autocast('cuda',enabled=amp,dtype=torch.float16):return m.sequence(x,h)
            def backward():
                m.zero_grad(set_to_none=True);x.grad=None;h.grad=None
                with torch.autocast('cuda',enabled=amp,dtype=torch.float16):y,_=m.sequence(x,h)
                (y.float()*weight).mean().backward()
            row=dict(kind=name,batch=batch,length=t,amp=amp,forward=timed(forward),forward_backward=timed(backward))
            micro.append(row);print('recurrent',row,flush=True)
            del m,x,h;torch.cuda.empty_cache()
    for amp,batch,prepared in [(False,256,False),(True,4096,True)]:
        for name,factory in factories:
            torch.manual_seed(97);m,train=workload(True,amp,batch,prepared,model_factory=factory)
            train_time=timed(train,30)
            missing=[n for n,p in m.named_parameters() if p.grad is None]
            assert not missing, 'Missing training gradients: '+str(missing)
            assert all(torch.isfinite(p.grad).all() for p in m.parameters())
            g,mask,s=inputs(512);h=torch.zeros(512,128,device='cuda')
            @torch.no_grad()
            def infer():
                with torch.autocast('cuda',enabled=amp,dtype=torch.float16):
                    logits,z=m.step_features(m.encode(g,s),mask,h);v=m.value(z)
                return torch.distributions.Categorical(logits=logits).sample(),v
            inf=timed(infer,30)
            row=dict(kind=name,amp=amp,batch=batch,prepared=prepared,optimizer=train_time,inference=inf,network_only_four_pass_decisions_per_second=1000/(inf['ms']/512+4*train_time['ms']/batch))
            full.append(row);print('whole',row,flush=True)
            assert all(torch.isfinite(p).all() for p in m.parameters())
            del train,m;torch.cuda.empty_cache()
    save_json(ROOT/('results/symbolic-mingru-scan-benchmark'+('-reverse' if args.reverse else '')+'.json'),dict(reverse_order=args.reverse,recurrent=micro,whole_network=full,device=torch.cuda.get_device_name(),torch=torch.__version__,other_gpu_processes=other,scope='Median of three timing rounds, compilation/warmup excluded. Micro: projection plus recurrence, no CNN or optimizer. Whole: 80x70 observations, 16 burn + 16 learn, four PPO-shaped passes; no simulator/GAE/actual PPO.'))

if __name__=='__main__':main()
