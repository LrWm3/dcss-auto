"""Encoder optimization: checkpoint, feature, gradient and padded-loss parity."""
import copy
import torch
from torch.nn import functional as F
from symbolic_fast import FastSymbolicPolicy,SkipIdentityPool
from symbolic_run import Sequences


def main():
    torch.set_num_threads(1);torch.manual_seed(871)
    # The bypass must also preserve pooling semantics for future non-4x4 inputs.
    for size in (4,5,7):
        x=torch.randn(3,24,size,size,device='cuda',requires_grad=True)
        a=SkipIdentityPool(4)(x);b=F.adaptive_avg_pool2d(x,4)
        torch.testing.assert_close(a,b,rtol=0,atol=0)
        torch.testing.assert_close(torch.autograd.grad(a.sum(),x)[0],torch.autograd.grad(b.sum(),x)[0],rtol=0,atol=0)
    x=torch.randn(3,24,4,4,device='cuda')
    torch.testing.assert_close(SkipIdentityPool(2)(x),F.adaptive_avg_pool2d(x,2),rtol=0,atol=0)
    base=FastSymbolicPolicy().cuda()
    for skip,layout in [(True,False),(False,True),(True,True)]:
        m=copy.deepcopy(base).configure_encoder(skip,layout)
        assert list(base.state_dict())==list(m.state_dict())
        assert sum(p.numel() for p in base.parameters())==sum(p.numel() for p in m.parameters())
        for h,w in [(32,32),(70,80)]:
            g=torch.randint(0,2,(8,11,h,w),device='cuda',dtype=torch.uint8)*255
            s=torch.tensor([[1.,.1,0.,0.],[.5,.4,w-1.,h-1.],[.7,.2,15.,16.],[1.,.7,w//2,h//2]],device='cuda').repeat(2,1)
            inputs=base.prepare(g,s)
            for amp in (False,True):
                base.zero_grad();m.zero_grad()
                with torch.autocast('cuda',enabled=amp,dtype=torch.float16):
                    a=base.encode_prepared(inputs);b=m.encode_prepared(inputs)
                tol=2e-3 if amp else 2e-5
                torch.testing.assert_close(a,b,atol=tol,rtol=tol)
                weights=torch.randn_like(a)
                (a*weights).mean().backward();(b*weights).mean().backward()
                for name,p in base.named_parameters():
                    q=dict(m.named_parameters())[name]
                    if p.grad is not None:torch.testing.assert_close(p.grad,q.grad,atol=tol,rtol=tol)
            with torch.no_grad():torch.testing.assert_close(m.encode(g,s),m.encode_prepared(inputs),atol=2e-5,rtol=2e-5)
        buf=Sequences(4);buf.n=4;buf.g.zero_();buf.g[:,:,0]=255;buf.g[:,:,5,16,16]=255
        buf.m.fill_(1);buf.s.copy_(torch.tensor([1.,.2,16.,16.],device='cuda'));buf.y.fill_(0);buf.v.fill_(True)
        buf.v[0,:16]=False;buf.v[1,24:]=False;buf.v[2,:16]=False;buf.v[2,20:]=False
        base.zero_grad();m.zero_grad()
        torch.manual_seed(18);a,na=buf.loss(base,4);a.backward()
        torch.manual_seed(18);b,nb=buf.loss(m,4);b.backward()
        assert na==nb
        torch.testing.assert_close(a,b,atol=2e-5,rtol=2e-5)
        for p,q in zip(base.parameters(),m.parameters()):
            if p.grad is not None:torch.testing.assert_close(p.grad,q.grad,atol=2e-5,rtol=2e-4)
        print('PASS',dict(skip_pool=skip,channels_last=layout),'feature/gradient/padded replay parity',flush=True)
    print('PASS checkpoint schema and parameter count unchanged; identity and nonidentity pooling',flush=True)

if __name__=='__main__':main()
