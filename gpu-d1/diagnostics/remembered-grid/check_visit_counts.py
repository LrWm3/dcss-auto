"""Check visit counts independently and guard against stale cached histories."""
import torch
from compact_policy import CompactPolicy,ExactCache,count_map

def main():
    torch.set_num_threads(1);torch.manual_seed(32)
    for block in [2,4]:
        for h,w in [(1,1),(7,9),(32,32),(70,80)]:
            t=torch.randint(0,2,(2,4,h,w),dtype=torch.uint8)*255
            out=count_map(t,block,visits=True)
            assert torch.equal(out[:,:5],count_map(t[:,:3],block))
            expected=torch.zeros_like(out[:,5])
            for y in range(h):
                for x in range(w):expected[:,y//block,x//block]+=(t[:,3,y,x]>0).float()/(block*block)
            assert torch.equal(out[:,5],expected)
    for kind in ['counts_visits','counts2_visits']:
        m=CompactPolicy(kind)
        for h,w in [(32,32),(70,80)]:
            g=torch.zeros(2,11,h,w,dtype=torch.uint8);g[:,0]=255;g[:,3]=255
            s=torch.tensor([[1.,.1,10.,10.],[1.,.1,11.,11.]]);mask=torch.ones(2,19)
            cache=ExactCache(m)
            with torch.no_grad():
                assert torch.allclose(m(g,mask,s),cache(g,mask,s),atol=1e-6)
                s[:,2]+=1;cache(g,mask,s);assert cache.refreshes==2
                # A newly visited floor requires refresh even if no terrain is revealed.
                g[0,2,10,11]=255
                assert torch.allclose(m(g,mask,s),cache(g,mask,s),atol=1e-6);assert cache.refreshes==3
                assert cache.memory[0,5,10//m.block,11//m.block]==1/(m.block*m.block)
                cache(g,mask,s);assert cache.refreshes==3
                # Current visibility and enemy channels must not enter global summaries.
                old=m.encode_map(m.terrain(g));g[:,3]=0;g[:,6:]=255
                assert torch.equal(old,m.encode_map(m.terrain(g)))
            m(g,mask,s).square().mean().backward()
            assert all(torch.isfinite(p.grad).all() for p in m.parameters() if p.grad is not None)
        # Visit channel transforms with the rest of the map under D4 augmentation.
        t=torch.randint(0,2,(1,4,32,32),dtype=torch.uint8)*255
        base=count_map(t,m.block,visits=True)
        for group in range(8):
            a=t.flip(-1) if group>=4 else t;b=base.flip(-1) if group>=4 else base
            assert torch.equal(count_map(torch.rot90(a,group%4,(-2,-1)),m.block,visits=True),torch.rot90(b,group%4,(-2,-1)))
        print('PASS',kind,flush=True)
    print('PASS visit counts, partial blocks, transforms, cache invalidation, input isolation and gradients')
if __name__=='__main__':main()
