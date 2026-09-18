"""Uncontended full-size FP32 network benchmark, with recurrent burn-in accounted."""
import json,os,subprocess,time
import torch
from torch.nn import functional as F
from run import save_json
from runtime import OUT,ROOT
from symbolic_policy import SymbolicPolicy

def main():
    torch.set_num_threads(1);torch.backends.cudnn.benchmark=True;torch.manual_seed(97)
    def others():return [x for x in subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True).strip().splitlines() if x.split(',')[0].strip()!=str(os.getpid())]
    assert not others(), 'Refuse competing GPU jobs'
    rows=[]
    for kind in ['ff','gru']:
        m=SymbolicPolicy(kind=='gru').cuda();m.load_state_dict(torch.load(OUT/f'symbolic-{kind}/best.pt',weights_only=False)['model'])
        def inputs(n):
            g=torch.zeros(n,11,70,80,device='cuda',dtype=torch.uint8);r=torch.randint(0,4,(n,70,80),device='cuda')
            g[:,0]=((r==2)|(r==3)).byte()*255;g[:,1]=(r==1).byte()*255;g[:,2]=(r==3).byte()*255;g[:,3]=255;g[:,4,10,10]=255
            return g,torch.ones(n,19,device='cuda'),torch.tensor([1.,.1,40.,35.],device='cuda').repeat(n,1)
        def timed(fn):
            for _ in range(10):fn()
            torch.cuda.synchronize();t=time.monotonic()
            for _ in range(30):fn()
            torch.cuda.synchronize();return (time.monotonic()-t)/30
        g,mask,s=inputs(512);h=torch.zeros(512,128,device='cuda')
        @torch.no_grad()
        def infer():
            z,state=m.step_features(m.encode(g,s),mask,h);return torch.distributions.Categorical(logits=z).sample(),m.value(state)
        inf=timed(infer);del g,mask,s,h
        # 16 sequences x 16 learning steps = 256 decisions; GRU also uses 16 burn-in steps.
        g,mask,s=inputs(256);gb,mb,sb=inputs(256);opt=torch.optim.Adam(m.parameters(),lr=1e-5)
        with torch.no_grad():
            oldz=m(g,mask,s);dist=torch.distributions.Categorical(logits=oldz);action=dist.sample();oldlp=dist.log_prob(action);adv=torch.randn(256,device='cuda');ret=torch.randn(256,device='cuda')
        def train():
            opt.zero_grad(set_to_none=True);h=None
            if m.recurrent:
                with torch.no_grad():
                    burn=m.encode(gb,sb).reshape(16,16,-1);h=burn.new_zeros(16,128)
                    for t in range(16):_,h=m.step_features(burn[:,t],mb.reshape(16,16,19)[:,t],h)
            x=m.encode(g,s)
            if m.recurrent:
                x=x.reshape(16,16,-1);zs=[];vs=[]
                for t in range(16):
                    z,h=m.step_features(x[:,t],mask.reshape(16,16,19)[:,t],h);zs.append(z);vs.append(m.value(h).squeeze(-1))
                logits=torch.stack(zs,1).reshape(-1,19);v=torch.stack(vs,1).reshape(-1)
            else:logits,z=m.step_features(x,mask);v=m.value(z).squeeze(-1)
            d=torch.distributions.Categorical(logits=logits);ratio=(d.log_prob(action)-oldlp).exp();loss=-torch.minimum(ratio*adv,ratio.clamp(.8,1.2)*adv).mean()+.25*(v-ret).square().mean()-.001*d.entropy().mean()
            loss.backward();torch.nn.utils.clip_grad_norm_(m.parameters(),.5);opt.step()
        trainsec=timed(train)
        assert all(torch.isfinite(p).all() for p in m.parameters())
        rows.append(dict(kind=kind,parameters=sum(p.numel() for p in m.parameters()),inference_batch=512,learning_decisions_per_batch=256,inference_ms=inf*1000,optimizer_ms=trainsec*1000,network_only_four_pass_decisions_per_second=1/(inf/512+4*trainsec/256)))
        print(rows[-1],flush=True)
    save_json(ROOT/'results/remembered-grid-symbolic-performance.json',dict(rows=rows,shape=[70,80],precision='FP32',device=torch.cuda.get_device_name(),scope='Network-only synthetic cost, not PPO learning or end-to-end speed. Includes per-call symbolic preprocessing, four optimizer passes, and GRU 16-step burn-in plus 16-step truncated gradients. Synthetic advantages/returns; no meaningful learning claim. Previous compact benchmarks used AMP and batch 1024, so raw speed is not a matched benchmark comparison.',other_gpu_processes_at_end=others()))
if __name__=='__main__':main()
