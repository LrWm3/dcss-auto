"""Matched full-map network benchmark; not an end-to-end PPO speed claim."""
import time
import torch
from optimize_symbolic import workload,inputs
from symbolic_fast import FastSymbolicPolicy
from symbolic_mingru import MinSymbolicPolicy
from run import save_json
from runtime import ROOT


def timed(fn):
    for _ in range(10):fn()
    torch.cuda.synchronize();start=time.monotonic()
    for _ in range(30):fn()
    torch.cuda.synchronize();return (time.monotonic()-start)/30


def main():
    torch.set_num_threads(1);torch.backends.cudnn.benchmark=True;rows=[]
    for amp,batch,prepared in [(False,256,False),(True,4096,True)]:
        for name,factory in [('gru',FastSymbolicPolicy),('mingru',MinSymbolicPolicy)]:
            torch.manual_seed(97)
            m,train=workload(True,amp,batch,prepared,model_factory=factory)
            trainsec=timed(train);g,mask,s=inputs(512);h=torch.zeros(512,128,device='cuda')
            @torch.no_grad()
            def infer():
                with torch.autocast('cuda',enabled=amp,dtype=torch.float16):
                    logits,z=m.step_features(m.encode(g,s),mask,h);v=m.value(z)
                return torch.distributions.Categorical(logits=logits).sample(),v
            inf=timed(infer)
            row=dict(kind=name,amp=amp,batch=batch,prepared=prepared,parameters=sum(p.numel() for p in m.parameters()),optimizer_ms=trainsec*1000,inference_ms=inf*1000,network_only_four_pass_decisions_per_second=1/(inf/512+4*trainsec/batch))
            rows.append(row);print(row,flush=True)
            assert all(torch.isfinite(p).all() for p in m.parameters())
            del train,m;torch.cuda.empty_cache()
    save_json(ROOT/'results/symbolic-mingru-benchmark.json',dict(rows=rows,device=torch.cuda.get_device_name(),torch=torch.__version__,scope='80x70 network only; 16 burn + 16 learning steps; four PPO-shaped passes, no environment or real PPO training. Both networks freshly initialized; same workload, no competing GPU jobs.'))

if __name__=='__main__':main()
