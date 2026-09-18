"""Fused CUDA minGRU affine scan, with an analytic reverse-scan backward.

Projection stays in PyTorch (GEMM); pointwise gates/candidates and recurrence are
fused. FP32 recurrent states, including under AMP. No episode resets inside a
sequence; the caller owns reset and terminal padding, as for the eager core.
"""
import torch
import triton
import triton.language as tl


@triton.jit
def _compose(a1, b1, a2, b2):
    return a2 * a1, b2 + a2 * b1


@triton.jit
def _forward(P, H0, Y, T: tl.constexpr, H: tl.constexpr,
             BT: tl.constexpr, BH: tl.constexpr):
    batch = tl.program_id(0)
    hs = tl.program_id(1) * BH + tl.arange(0, BH)
    ts = tl.arange(0, BT)
    valid = (ts[:, None] < T) & (hs[None, :] < H)
    off = (batch * T + ts[:, None]) * (2 * H) + hs[None, :]
    c = tl.load(P + off, valid, 0).to(tl.float32)
    u = tl.load(P + off + H, valid, 0).to(tl.float32)
    a = tl.sigmoid(-u)
    z = tl.sigmoid(u)
    g = tl.where(c >= 0, c + .5, tl.sigmoid(c))
    a = tl.where(valid, a, 1.)
    b = tl.where(valid, z * g, 0.)
    aa, bb = tl.associative_scan((a, b), 0, _compose)
    h0 = tl.load(H0 + batch * H + hs, hs < H, 0)
    y = bb + aa * h0[None, :]
    tl.store(Y + (batch * T + ts[:, None]) * H + hs[None, :], y, valid)


@triton.jit
def _backward(P, H0, Y, DY, DP, DH0, T: tl.constexpr, H: tl.constexpr,
              BT: tl.constexpr, BH: tl.constexpr):
    batch = tl.program_id(0)
    hs = tl.program_id(1) * BH + tl.arange(0, BH)
    # Reversed time: a_next is the coefficient of the following adjoint.
    ts = T - 1 - tl.arange(0, BT)
    valid = (ts[:, None] >= 0) & (hs[None, :] < H)
    off = (batch * T + ts[:, None]) * (2 * H) + hs[None, :]
    c = tl.load(P + off, valid, 0).to(tl.float32)
    u = tl.load(P + off + H, valid, 0).to(tl.float32)
    nxt = tl.load(P + off + 2 * H + H,
                  valid & (ts[:, None] + 1 < T), 0).to(tl.float32)
    a_next = tl.where(valid & (ts[:, None] + 1 < T), tl.sigmoid(-nxt), 0.)
    dy = tl.load(DY + (batch * T + ts[:, None]) * H + hs[None, :], valid, 0)
    _, adjoint = tl.associative_scan((a_next, dy), 0, _compose)
    prev = tl.load(Y + (batch * T + ts[:, None] - 1) * H + hs[None, :],
                   valid & (ts[:, None] > 0), 0)
    h0 = tl.load(H0 + batch * H + hs, hs < H, 0)
    prev = tl.where(ts[:, None] == 0, h0[None, :], prev)
    sigmoid_c = tl.sigmoid(c)
    g = tl.where(c >= 0, c + .5, sigmoid_c)
    dg = tl.where(c >= 0, 1., sigmoid_c * (1. - sigmoid_c))
    z = tl.sigmoid(u)
    a = tl.sigmoid(-u)
    dc = adjoint * z * dg
    du = adjoint * z * a * (g - prev)
    tl.store(DP + off, dc, valid)
    tl.store(DP + off + H, du, valid)
    initial_grad = tl.sum(tl.where(ts[:, None] == 0, adjoint * a, 0.), axis=0)
    tl.store(DH0 + batch * H + hs, initial_grad, hs < H)


class _Scan(torch.autograd.Function):
    @staticmethod
    def forward(ctx, projection, h0):
        p = projection.contiguous();h0 = h0.contiguous()
        b, t, width = p.shape;h = width // 2
        y = torch.empty((b,t,h),device=p.device,dtype=torch.float32)
        _forward[(b,triton.cdiv(h,32))](p,h0,y,t,h,triton.next_power_of_2(t),32)
        ctx.save_for_backward(p,h0,y)
        return y

    @staticmethod
    @torch.autograd.function.once_differentiable
    def backward(ctx, dy):
        p,h0,y = ctx.saved_tensors;b,t,h = y.shape
        dp = torch.empty_like(p);dh0 = torch.empty_like(h0)
        _backward[(b,triton.cdiv(h,32))](p,h0,y,dy.contiguous(),dp,dh0,t,h,triton.next_power_of_2(t),32)
        return dp,dh0


def scan(projection, h0=None):
    b,t,width=projection.shape
    if t < 1 or width % 2 or not projection.is_cuda:
        raise ValueError('Expected CUDA [batch, nonempty time, 2*hidden] projection')
    if projection.dtype not in (torch.float16,torch.bfloat16,torch.float32):
        raise ValueError('Fused scan supports FP16/BF16 projections and FP32 recurrence')
    # Turing cannot execute native BF16 conversion instructions. Autograd
    # preserves the cast back to the caller's projection dtype.
    if projection.dtype == torch.bfloat16 and torch.cuda.get_device_capability(projection.device)[0] < 8:
        projection = projection.float()
    if h0 is None:
        h0=torch.zeros(b,width//2,device=projection.device,dtype=torch.float32)
    if h0.shape != (b,width//2) or h0.dtype != torch.float32 or h0.device != projection.device:
        raise ValueError('Initial state must be FP32 [batch, hidden] on the same device')
    return _Scan.apply(projection,h0)
