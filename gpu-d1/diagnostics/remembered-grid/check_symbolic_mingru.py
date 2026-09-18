"""Numerics, gradients, chunk continuity, autocast and real padded replay checks."""
import copy
import torch
from symbolic_mingru import MinGRU, MinSymbolicPolicy
from symbolic_run import Sequences


def compare(dtype, length, scale=1., initial=True, device='cpu', amp=False):
    torch.manual_seed(32)
    m = MinGRU(7, 9).to(device=device, dtype=dtype)
    x = (torch.randn(3, length, 7, device=device, dtype=dtype)*scale).requires_grad_()
    h = torch.rand(3, 9, device=device, dtype=dtype).requires_grad_() if initial else torch.zeros(3, 9, device=device, dtype=dtype, requires_grad=True)
    with torch.autocast(device, enabled=amp, dtype=torch.float16):
        seq, last = m.sequence(x, h)
        z = h; steps = []
        for t in range(length):
            z = m(x[:, t], z); steps.append(z)
        ref = torch.stack(steps, 1)
        cut = length//2
        left, mid = m.sequence(x[:, :cut], h)
        right, _ = m.sequence(x[:, cut:], mid)
    tol = 2e-10 if dtype == torch.float64 else 3e-3 if amp else 3e-4
    torch.testing.assert_close(seq, ref, atol=tol, rtol=tol)
    torch.testing.assert_close(seq, torch.cat([left, right], 1), atol=tol, rtol=tol)
    params = (x, h, *m.parameters())
    weights = torch.randn_like(seq)
    a = torch.autograd.grad((seq*weights).mean(), params, retain_graph=True)
    b = torch.autograd.grad((ref*weights).mean(), params)
    for lhs, rhs in zip(a, b):
        assert torch.isfinite(lhs).all()
        torch.testing.assert_close(lhs, rhs, atol=tol, rtol=tol)
    assert torch.isfinite(last).all()


def main():
    torch.set_num_threads(1)
    for dtype in (torch.float64, torch.float32):
        for length, scale in ((32,1), (256,1), (32,30)):
            for initial in (False,True):compare(dtype,length,scale,initial)
    # One-step scan and zero-state derivatives must remain well-defined.
    m=MinGRU(2,3).double();x=torch.zeros(1,1,2,dtype=torch.float64);h=torch.zeros(1,3,dtype=torch.float64,requires_grad=True)
    z,last=m.sequence(x,h)
    torch.testing.assert_close(last,m(x[:,0],h))
    torch.testing.assert_close(torch.autograd.grad(z.sum(),h)[0],torch.full_like(h,.5))
    for shape in [(1,0,2),(1,2)]:
        try:m.sequence(torch.zeros(shape,dtype=torch.float64))
        except ValueError:pass
        else:raise AssertionError('invalid sequence accepted')
    # Explicit previous overflow regression: constant z=.99 over 32 steps.
    m=MinGRU(1,1)
    with torch.no_grad():m.linear.weight.copy_(torch.tensor([[0.],[torch.logit(torch.tensor(.99))]]))
    states,_=m.sequence(torch.ones(1,32,1))
    torch.testing.assert_close(states[0,-1,0],torch.tensor(.5),atol=1e-5,rtol=1e-5)
    compare(torch.float32,32,device='cuda',amp=True)
    compare(torch.float32,256,device='cuda',amp=True)
    # Real replay's invalid burn-in and terminal suffix must give equivalent losses
    # and gradients under the sequence and step APIs.
    torch.manual_seed(84)
    fast=MinSymbolicPolicy().cuda();slow=copy.deepcopy(fast)
    slow.sequence=None
    class StepOnly(torch.nn.Module):
        def __init__(self, model):super().__init__();self.model=model;self.recurrent=True
        def encode(self,*args):return self.model.encode(*args)
        def step_features(self,*args):return self.model.step_features(*args)
    slow=StepOnly(slow)
    replay=Sequences(capacity=4);replay.n=4
    replay.g.zero_();replay.g[:,:,0]=255;replay.g[:,:,5,16,16]=255
    replay.m.fill_(1);replay.s.copy_(torch.tensor([1.,.2,16.,16.],device='cuda'));replay.y.fill_(0);replay.v.fill_(True)
    replay.v[0,:16]=False;replay.v[1,24:]=False;replay.v[2,:16]=False;replay.v[2,20:]=False
    torch.manual_seed(18);a,na=replay.loss(fast,4);a.backward()
    torch.manual_seed(18);b,nb=replay.loss(slow,4);b.backward()
    assert na==nb
    torch.testing.assert_close(a,b,atol=1e-5,rtol=1e-5)
    for p,q in zip(fast.parameters(),slow.parameters()):
        if p.grad is not None:torch.testing.assert_close(p.grad,q.grad,atol=2e-5,rtol=2e-4)
    print('PASS: outputs, input/state/weight gradients, zero/nonzero states, chunks, extreme gates, FP16 autocast and padded replay')

if __name__=='__main__':main()
