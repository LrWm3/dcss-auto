"""Profile and compare symbolic GRU implementations on full-size inputs."""
import argparse,json,time,os,subprocess,hashlib
import torch
from run import save_json,evaluate
from runtime import OUT,ROOT
from symbolic_policy import SymbolicPolicy,Stateful
from symbolic_fast import FastSymbolicPolicy

def load(fast=False):
    m=(FastSymbolicPolicy() if fast else SymbolicPolicy(True)).cuda()
    ck=torch.load(OUT/'symbolic-gru/best.pt',weights_only=False)['model'];m.load_state_dict(ck,strict=not fast)
    return m

def inputs(n):
    g=torch.zeros(n,11,70,80,device='cuda',dtype=torch.uint8);r=torch.randint(0,4,(n,70,80),device='cuda');g[:,0]=((r==2)|(r==3)).byte()*255;g[:,1]=(r==1).byte()*255;g[:,2]=(r==3).byte()*255;g[:,3]=255;g[:,4,10,10]=255
    return g,torch.ones(n,19,device='cuda'),torch.tensor([1.,.1,40.,35.],device='cuda').repeat(n,1)

def workload(fast=False,amp=False,batch=256,prepared=False):
    m=load(fast);opt=torch.optim.Adam(m.parameters(),lr=1e-5);scaler=torch.amp.GradScaler('cuda',enabled=amp)
    g,mask,s=inputs(batch);gb,mb,sb=inputs(batch);n=batch//16
    if prepared:
        with torch.no_grad():p=m.prepare(g,s);pb=m.prepare(gb,sb)
    action=torch.zeros(batch,dtype=torch.long,device='cuda');oldlp=torch.full((batch,),-3.,device='cuda');adv=torch.randn(batch,device='cuda');ret=torch.randn(batch,device='cuda')
    def enc(g,s,p=None):return m.encode_prepared(p) if p is not None else m.encode(g,s)
    def train():
        opt.zero_grad(set_to_none=True)
        with torch.autocast('cuda',enabled=amp,dtype=torch.float16):
            with torch.no_grad():
                burn=enc(gb,sb,pb if prepared else None).reshape(n,16,-1)
                if fast:_,h=m.sequence(burn)
                else:
                    h=burn.new_zeros(n,128)
                    for t in range(16):_,h=m.step_features(burn[:,t],mb.reshape(n,16,19)[:,t],h)
            x=enc(g,s,p if prepared else None).reshape(n,16,-1)
            if fast:z,_=m.sequence(x,h)
            else:
                zs=[];vs=[]
                for t in range(16):
                    logits,h=m.step_features(x[:,t],mask.reshape(n,16,19)[:,t],h);zs.append(logits);vs.append(m.value(h).squeeze(-1))
                logits=torch.stack(zs,1).reshape(batch,19);v=torch.stack(vs,1).reshape(batch).float()
            if fast:
                z=z.reshape(batch,128);logits=m.policy(z).float().masked_fill(mask==0,-1e9);v=m.value(z).float().squeeze(-1)
        d=torch.distributions.Categorical(logits=logits);ratio=(d.log_prob(action)-oldlp).exp();loss=-torch.minimum(ratio*adv,ratio.clamp(.8,1.2)*adv).mean()+.25*(v-ret).square().mean()-.001*d.entropy().mean()
        scaler.scale(loss).backward();scaler.unscale_(opt);torch.nn.utils.clip_grad_norm_(m.parameters(),.5);scaler.step(opt);scaler.update()
    return m,train

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--profile',action='store_true');args=ap.parse_args();torch.set_num_threads(1);torch.manual_seed(97);torch.backends.cudnn.benchmark=True
    other=[x for x in subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True).strip().splitlines() if x.split(',')[0].strip()!=str(os.getpid())]
    assert not other, 'Refuse competing GPU jobs: '+str(other)
    if args.profile:
        m,train=workload()
        for _ in range(10):train()
        with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as p:
            for _ in range(5):train()
        (OUT/'symbolic-profile.txt').write_text(p.key_averages().table(sort_by='self_cuda_time_total',row_limit=35));print((OUT/'symbolic-profile.txt').read_text());return
    rows=[]
    def timed(fn):
        for _ in range(10):fn()
        torch.cuda.synchronize();t=time.monotonic()
        for _ in range(30):fn()
        torch.cuda.synchronize();return (time.monotonic()-t)/30
    for fast,amp,batch,prepared in [(False,False,256,False),(True,False,256,False),(True,True,256,False),(True,True,1024,False),(True,True,1024,True),(True,True,2048,True),(True,True,4096,True)]:
        m,train=workload(fast,amp,batch,prepared);trainsec=timed(train)
        g,mask,s=inputs(512)
        @torch.no_grad()
        def infer():
            with torch.autocast('cuda',enabled=amp,dtype=torch.float16):
                x=m.encode(g,s);logits,h=m.step_features(x,mask);v=m.value(h)
            return torch.distributions.Categorical(logits=logits).sample(),v
        inf=timed(infer)
        row=dict(fast=fast,amp=amp,batch=batch,precomputed_symbolic_inputs=prepared,optimizer_ms=trainsec*1000,inference_ms=inf*1000,network_only_four_pass_decisions_per_second=1/(inf/512+4*trainsec/batch));rows.append(row);print(row,flush=True)
        assert all(torch.isfinite(p).all() for p in m.parameters());del train,m;torch.cuda.empty_cache()
    save_json(ROOT/'results/symbolic-optimization-benchmark.json',dict(rows=rows,device=torch.cuda.get_device_name(),torch=torch.__version__,source_sha256=hashlib.sha256(__import__('pathlib').Path(__file__).read_bytes()).hexdigest(),other_gpu_processes_at_start=other,scope='Network only, full80x70, four PPO-shaped optimizer passes; recurrent16burn+16learn; no simulator. Prepared mode caches only deterministic symbolic inputs, not learned features. Larger batches change update granularity.'))
if __name__=='__main__':main()
