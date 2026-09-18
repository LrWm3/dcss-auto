import torch
from symbolic_policy import SymbolicPolicy
from symbolic_fast import FastSymbolicPolicy

def main():
    torch.set_num_threads(1);torch.manual_seed(12)
    a=SymbolicPolicy(True).cuda();b=FastSymbolicPolicy().cuda();b.load_state_dict(a.state_dict(),strict=False)
    assert sum(p.numel() for p in a.parameters())==sum(p.numel() for p in b.parameters())
    for h,w in [(32,32),(70,80)]:
        g=torch.randint(0,2,(4,11,h,w),device='cuda',dtype=torch.uint8)*255;s=torch.tensor([[1.,.1,0.,0.],[1.,.2,w-1.,h-1.],[.5,.1,15.,16.],[.8,.2,10.,10.]],device='cuda')
        with torch.no_grad():assert torch.allclose(a.encode(g,s),b.encode(g,s),atol=1e-6)
    x=torch.randn(4,16,194,device='cuda',requires_grad=True);xx=x.detach().clone().requires_grad_();h=torch.randn(4,128,device='cuda');hs=[]
    for t in range(16):h=a.core(x[:,t],h);hs.append(h)
    # Repeat with matching initial state for exact sequence comparison.
    h0=torch.randn(4,128,device='cuda');h=h0;hs=[]
    for t in range(16):h=a.core(x[:,t],h);hs.append(h)
    ref=torch.stack(hs,1);fast,last=b.sequence(xx,h0);assert torch.allclose(ref,fast,atol=2e-6);assert torch.allclose(h,last,atol=2e-6)
    ref.square().mean().backward();fast.square().mean().backward();assert torch.allclose(x.grad,xx.grad,atol=1e-7)
    for name in ['weight_ih','weight_hh','bias_ih','bias_hh']:
        assert torch.allclose(getattr(a.core,name).grad,getattr(b.core,name).grad,atol=1e-6)
    from symbolic_run import Sequences,collect
    from runtime import Env,build
    build();e=Env(batch=16);buf=Sequences(128);collect(e,buf,steps=65)
    valid=buf.v[:buf.n];assert torch.equal(valid[:,:16].any(1),valid[:,:16].all(1));assert not ((~valid[:,16:-1])&valid[:,17:]).any()
    a.zero_grad();b.zero_grad();torch.manual_seed(231);la,na=buf.loss(a);torch.manual_seed(231);lb,nb=buf.loss(b)
    assert na==nb and torch.allclose(la,lb,atol=1e-6)
    la.backward();lb.backward()
    for name,p in a.named_parameters():
        q=dict(b.named_parameters())[name]
        if p.grad is not None:assert torch.allclose(p.grad,q.grad,atol=2e-6),name
    print('PASS padded sequence replay loss and all learned gradients')
    print('PASS exact preprocessing at boundaries/full sizes, unchanged parameter count, fused sequence outputs and gradients')
if __name__=='__main__':main()
