"""Check count semantics, position sensitivity, fresh-cache parity and gradients."""
import torch
from compact_policy import CompactPolicy,ExactCache,count_map

def main():
    torch.set_num_threads(1);torch.manual_seed(17)
    terrain=torch.zeros(1,3,7,9,dtype=torch.uint8);terrain[:,1]=255;terrain[:,1,2:5,2:7]=0;terrain[:,0,2:5,2:7]=255;terrain[:,1,1,4]=0;terrain[:,2,3,3]=255
    actual=count_map(terrain)*16;expected=torch.zeros(1,5,2,3)
    for y in range(7):
        for x in range(9):
            floor=bool(terrain[0,0,y,x]);wall=bool(terrain[0,1,y,x]);frontier=floor and any(not bool(terrain[0,:2,yy,xx].any()) for yy in range(max(0,y-1),min(7,y+2)) for xx in range(max(0,x-1),min(9,x+2)))
            expected[0,:,y//4,x//4]+=torch.tensor([floor or wall,frontier,floor,wall,bool(terrain[0,2,y,x])])
    assert torch.equal(actual,expected)
    # Distinct fully observed geometry with identical block totals is intentionally aliased.
    a=torch.zeros(1,3,8,8,dtype=torch.uint8);a[:,1]=255;a[:,0,1,1:3]=255;a[:,1,1,1:3]=0
    b=a.clone();b[:,0,1,1:3]=0;b[:,1,1,1:3]=255;b[:,0,2,1:3]=255;b[:,1,2,1:3]=0
    assert torch.equal(count_map(a),count_map(b))
    for kind in ['attn','coarse','counts']:
        m=CompactPolicy(kind)
        for h,w in [(32,32),(70,80)]:
            g=torch.zeros(2,11,h,w,dtype=torch.uint8);g[:,0,1:-1,1:-1]=255;g[:,3]=255;g[:,4,3,3]=255
            stats=torch.tensor([[1.,.1,10.,10.],[1.,.1,0.,0.]]);mask=torch.ones(2,19);mask[:,8:16]=0;c=ExactCache(m)
            with torch.no_grad():
                assert torch.allclose(m(g,mask,stats),c(g,mask,stats),atol=1e-6)
                before=c(g,mask,stats);stats[:,2]+=1;after=c(g,mask,stats);assert c.refreshes==2;assert not torch.equal(before,after)
                g[0,4,4,4]=255;assert torch.allclose(m(g,mask,stats),c(g,mask,stats),atol=1e-6);assert c.refreshes==3
                c.reset_cache();assert c.snapshot is None
            loss=m(g,mask,stats)[:,:8].square().mean();loss.backward()
            grads=[p.grad for p in m.parameters() if p.grad is not None];assert grads and all(torch.isfinite(v).all() for v in grads)
        print('PASS',kind,flush=True)
    print('PASS exact observed counts, frontier boundaries, geometry aliasing, cache reset/change/position checks and gradients')
if __name__=='__main__':main()
