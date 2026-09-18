"""Lossless visited bits, transformed observations and cache correctness."""
import torch
from torch.nn import functional as F
from compact_policy import CompactPolicy,ExactCache,count_map

def main():
    torch.set_num_threads(1);torch.manual_seed(231)
    m=CompactPolicy('counts2_visit_bits')
    for h,w in [(1,1),(7,9),(32,32),(70,80)]:
        g=torch.randint(0,2,(2,11,h,w),dtype=torch.uint8)*255
        memory=m.encode_map(m.terrain(g))
        assert torch.equal(memory[:,:5],count_map(g[:,[0,1,4]],2))
        expected=torch.zeros_like(memory[:,5:])
        for y in range(h):
            for x in range(w):expected[:,(y%2)*2+x%2,y//2,x//2]=(g[:,2,y,x]>0).float()
        assert torch.equal(memory[:,5:],expected)
        assert torch.equal(F.pixel_shuffle(memory[:,5:],2)[:,:,:h,:w],(g[:,2:3]>0).float())
        for group in range(8):
            tr=g.flip(-1) if group>=4 else g;tr=torch.rot90(tr,group%4,(-2,-1))
            bits=m.encode_map(m.terrain(tr))[:,5:];hh,ww=tr.shape[-2:]
            assert torch.equal(F.pixel_shuffle(bits,2)[:,:,:hh,:ww],(tr[:,2:3]>0).float())
    # These have equal visited counts, but must have different bit summaries.
    g=torch.zeros(2,11,32,32,dtype=torch.uint8);g[:,0]=255;g[:,3]=255
    g[0,2,10,10]=255;g[1,2,11,11]=255
    mem=m.encode_map(m.terrain(g));assert torch.equal(mem[0,:5],mem[1,:5]);assert mem[0,5:].sum()==mem[1,5:].sum();assert not torch.equal(mem[0,5:],mem[1,5:])
    stats=torch.tensor([[1.,.1,10.,10.]]).repeat(2,1);mask=torch.ones(2,19);cache=ExactCache(m)
    with torch.no_grad():
        assert torch.allclose(m(g,mask,stats),cache(g,mask,stats),atol=1e-6)
        stats[:,2]+=1;cache(g,mask,stats);assert cache.refreshes==2
        g[0,2,10,11]=255;assert torch.allclose(m(g,mask,stats),cache(g,mask,stats),atol=1e-6);assert cache.refreshes==3
        cache(g,mask,stats);assert cache.refreshes==3
        old=m.encode_map(m.terrain(g));g[:,3]=0;g[:,6:]=255;assert torch.equal(old,m.encode_map(m.terrain(g)))
    m(g,mask,stats).square().mean().backward();assert all(torch.isfinite(p.grad).all() for p in m.parameters() if p.grad is not None)
    print('PASS exact bits, ordering, partial blocks, D4, distinct equal-count patterns, cache refresh, input isolation and gradients')
if __name__=='__main__':main()
