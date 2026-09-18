"""Compare fused forward/backward against eager scan and sequential recurrence."""
import argparse,copy
import torch
from mingru_scan import scan
from symbolic_mingru import MinGRU,MinSymbolicPolicy
from symbolic_run import Sequences


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--memory-only',action='store_true');args=parser.parse_args()
    torch.set_num_threads(1);torch.manual_seed(613)
    if args.memory_only:
        for batch,t,h in [(2,1,3),(2,7,37),(2,16,128),(3,129,17),(1,256,32)]:
            p=torch.randn(batch,t,2*h,device='cuda',requires_grad=True)
            h0=torch.rand(batch,h,device='cuda',requires_grad=True)
            scan(p,h0).sum().backward()
        torch.cuda.synchronize();print('PASS memory-boundary smoke');return
    worst=0.
    for t,h in [(1,3),(7,37),(16,128),(32,128),(129,17),(256,32)]:
        for dtype in (torch.float32,torch.float16,torch.bfloat16):
            for scale in (1.,30.):
                p=(torch.randn(3,t,2*h,device='cuda')*scale).to(dtype).requires_grad_()
                h0=torch.rand(3,h,device='cuda',requires_grad=True)
                # Exercise noncontiguous projection and initial state, zeros,
                # candidate branch boundary and saturated gates.
                if scale==30.:
                    with torch.no_grad():p[:,:,0]=0;h0.zero_()
                y=scan(p,h0)
                c,u=p.float().chunk(2,-1);g=torch.where(c>=0,c+.5,c.sigmoid())
                z=h0;steps=[]
                for i in range(t):z=(-u[:,i]).sigmoid()*z+u[:,i].sigmoid()*g[:,i];steps.append(z)
                ref=torch.stack(steps,1)
                torch.testing.assert_close(y,ref,atol=2e-4,rtol=2e-5)
                w=torch.randn_like(y)
                lhs=torch.autograd.grad((y*w).sum(),(p,h0),retain_graph=True)
                rhs=torch.autograd.grad((ref*w).sum(),(p,h0))
                for a,b in zip(lhs,rhs):
                    assert torch.isfinite(a).all()
                    torch.testing.assert_close(a,b,atol=.04 if dtype==torch.bfloat16 else .005 if dtype==torch.float16 else 5e-4,rtol=.01 if dtype==torch.bfloat16 else .002 if dtype==torch.float16 else 5e-4)
                worst=max(worst,float((y-ref).abs().max()))
                if t>1:
                    cut=t//2
                    a=scan(p[:,:cut],h0);b=scan(p[:,cut:],a[:,-1])
                    torch.testing.assert_close(y,torch.cat([a,b],1),atol=2e-4,rtol=2e-5)
    print('PASS scan values, gradients, chunks, odd sizes, saturation and FP32/FP16/BF16; max output error',worst,flush=True)
    # Projected weight/input gradients under AMP, including carried memory.
    for amp in (False,True):
        eager=MinGRU(194,128).cuda();fused=copy.deepcopy(eager);fused.scan_backend='triton'
        x=torch.randn(8,16,194,device='cuda',requires_grad=True);xx=x.detach().clone().requires_grad_()
        h=torch.rand(8,128,device='cuda',requires_grad=True);hh=h.detach().clone().requires_grad_()
        with torch.autocast('cuda',enabled=amp,dtype=torch.float16):
            a,_=eager.sequence(x,h);b,_=fused.sequence(xx,hh)
        torch.testing.assert_close(a,b,atol=2e-5,rtol=2e-5)
        a.square().mean().backward();b.square().mean().backward()
        for p,q in [(x,xx),(h,hh),*zip(eager.parameters(),fused.parameters())]:
            torch.testing.assert_close(p.grad,q.grad,atol=2e-6,rtol=2e-3)
    # Existing training loss, initial burn-in padding, terminal suffix padding.
    eager=MinSymbolicPolicy().cuda();fused=copy.deepcopy(eager);fused.core.scan_backend='triton'
    buf=Sequences(4);buf.n=4;buf.g.zero_();buf.g[:,:,0]=255;buf.g[:,:,5,16,16]=255
    buf.m.fill_(1);buf.s.copy_(torch.tensor([1.,.2,16.,16.],device='cuda'));buf.y.fill_(0);buf.v.fill_(True)
    buf.v[0,:16]=False;buf.v[1,24:]=False;buf.v[2,:16]=False;buf.v[2,20:]=False
    torch.manual_seed(18);a,na=buf.loss(eager,4);a.backward()
    torch.manual_seed(18);b,nb=buf.loss(fused,4);b.backward()
    assert na==nb
    torch.testing.assert_close(a,b,atol=1e-5,rtol=1e-5)
    for p,q in zip(eager.parameters(),fused.parameters()):
        if p.grad is not None:torch.testing.assert_close(p.grad,q.grad,atol=2e-5,rtol=2e-4)
    # Optimizer smoke: both paths must make the same finite update.
    for model in (eager,fused):torch.optim.Adam(model.parameters(),lr=.0003).step()
    for p,q in zip(eager.parameters(),fused.parameters()):
        assert torch.isfinite(q).all()
        torch.testing.assert_close(p,q,atol=2e-5,rtol=2e-4)
    from optimize_symbolic import workload
    from symbolic_fast import FastSymbolicPolicy
    for factory in [FastSymbolicPolicy,MinSymbolicPolicy,lambda:MinSymbolicPolicy('triton')]:
        model,train=workload(True,True,32,True,model_factory=factory)
        for _ in range(3):train()
        missing=[n for n,p in model.named_parameters() if p.grad is None]
        assert not missing, 'AMP burn-in detached training weights: '+str(missing)
        assert all(torch.isfinite(p.grad).all() for p in model.parameters())
    print('PASS projected gradients, AMP, padded replay, optimizer update and AMP burn-in gradient regression',flush=True)

if __name__=='__main__':main()
