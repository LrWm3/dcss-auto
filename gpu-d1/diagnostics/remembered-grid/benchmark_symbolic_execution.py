"""Independent compilation/graph factors, same optimized encoder and GRU."""
import argparse,gc,os,subprocess,time
import torch
from symbolic_execution import StaticUpdate,StaticInference
from benchmark_mingru_scan import timed
from optimize_symbolic import inputs
from runtime import ROOT
from run import save_json

ARMS=[('eager',False,False),('compiled',True,False),('graphs',False,True),('compiled_graphs',True,True)]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--reverse',action='store_true');args=ap.parse_args()
    torch.set_num_threads(1);torch.backends.cudnn.benchmark=True
    other=[x for x in subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True).strip().splitlines() if x.split(',')[0].strip()!=str(os.getpid())]
    assert not other,other
    rows=[]
    path=ROOT/('results/symbolic-execution-benchmark'+('-reverse' if args.reverse else '')+'.json')
    for amp,batch,prepared in [(False,256,False),(True,4096,True)]:
        for name,compiled,graphed in reversed(ARMS) if args.reverse else ARMS:
            print('starting',name,'amp',amp,'batch',batch,flush=True)
            torch.manual_seed(97);u=StaticUpdate(batch,amp,prepared,compiled,graphed)
            start=time.perf_counter();u.step();torch.cuda.synchronize();setup=time.perf_counter()-start
            opt=timed(u.step,30)
            assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in u.model.parameters())
            g,mask,s=inputs(512);policy=StaticInference(u.execution,amp,graphed)
            @torch.no_grad()
            def infer():
                logits,v=policy.outputs(g,mask,s)
                return torch.distributions.Categorical(logits=logits,validate_args=False).sample(),v
            start=time.perf_counter();infer();torch.cuda.synchronize();infer_setup=time.perf_counter()-start
            inf=timed(infer,30)
            row=dict(arm=name,amp=amp,batch=batch,prepared=prepared,first_update_seconds=setup,first_inference_seconds=infer_setup,graph_setup_seconds=u.setup_seconds,optimizer=opt,inference=inf,network_only_four_pass_decisions_per_second=1000/(inf['ms']/512+4*opt['ms']/batch))
            rows.append(row);print(row,flush=True)
            save_json(path,dict(rows=rows,reverse_order=args.reverse,device=torch.cuda.get_device_name(),torch=torch.__version__,scope='80x70 network only; optimized channels-last/pooling GRU, 16 burn+16 learn, four PPO-shaped passes. Compile encoder/heads; explicit graph forward/backward, optimizer/scaler/clipping outside. Graph inference includes live input copies and carries hidden state. All gradients finite. Setup excluded from steady-state timing; no simulator/GAE/actual PPO.'))
            del infer,policy,u;gc.collect();torch.cuda.empty_cache()

if __name__=='__main__':main()
