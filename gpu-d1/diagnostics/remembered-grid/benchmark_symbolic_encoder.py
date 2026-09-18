"""Four-arm encoder ablation with full backward and isolated GPU timings."""
import argparse,os,subprocess
import torch
from symbolic_fast import FastSymbolicPolicy
from benchmark_mingru_scan import timed
from optimize_symbolic import workload,inputs
from runtime import ROOT
from run import save_json

ARMS=[('reference',False,False),('skip_pool',True,False),('channels_last',False,True),('both',True,True)]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--reverse',action='store_true');args=parser.parse_args()
    torch.set_num_threads(1);torch.backends.cudnn.benchmark=True
    other=[x for x in subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True).strip().splitlines() if x.split(',')[0].strip()!=str(os.getpid())]
    assert not other,other
    rows=[]
    for amp,batch,prepared in [(False,256,False),(True,4096,True)]:
        for name,skip,layout in reversed(ARMS) if args.reverse else ARMS:
            torch.manual_seed(97)
            m,train=workload(True,amp,batch,prepared,model_factory=lambda:FastSymbolicPolicy(True,skip,layout))
            opt=timed(train,30)
            assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in m.parameters())
            g,mask,s=inputs(512);h=torch.zeros(512,128,device='cuda')
            @torch.no_grad()
            def infer():
                with torch.autocast('cuda',enabled=amp,dtype=torch.float16):
                    logits,z=m.step_features(m.encode(g,s),mask,h);v=m.value(z)
                return torch.distributions.Categorical(logits=logits).sample(),v
            inf=timed(infer,30)
            row=dict(arm=name,amp=amp,batch=batch,prepared=prepared,optimizer=opt,inference=inf,network_only_four_pass_decisions_per_second=1000/(inf['ms']/512+4*opt['ms']/batch))
            rows.append(row);print(row,flush=True)
            del m,train;torch.cuda.empty_cache()
    save_json(ROOT/('results/symbolic-encoder-benchmark'+('-reverse' if args.reverse else '')+'.json'),dict(rows=rows,reverse_order=args.reverse,device=torch.cuda.get_device_name(),torch=torch.__version__,scope='80x70 whole-network benchmark, optimized GRU, 16 burn+16 learn, four PPO-shaped passes, no simulator/GAE. All parameters receive finite gradients. AMP burn/learn contexts separate. Medians of three rounds after warmup.'))

if __name__=='__main__':main()
