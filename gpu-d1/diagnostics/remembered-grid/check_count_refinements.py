"""Independent tile-level checks for smaller blocks and boundary crossings."""
import torch
from compact_policy import count_map,CompactPolicy,ExactCache
DIRECTIONS=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]
def expected(t,b):
    _,_,h,w=t.shape;out=torch.zeros(1,13,(h+b-1)//b,(w+b-1)//b)
    for y in range(h):
        for x in range(w):
            floor=bool(t[0,0,y,x]);wall=bool(t[0,1,y,x]);frontier=floor and any(not bool(t[0,:2,yy,xx].any()) for yy in range(max(0,y-1),min(h,y+2)) for xx in range(max(0,x-1),min(w,x+2)))
            out[0,:5,y//b,x//b]+=torch.tensor([floor or wall,frontier,floor,wall,bool(t[0,2,y,x])]).float()/(b*b)
            if not floor:continue
            for dx,dy in DIRECTIONS:
                xx,yy=x+dx,y+dy
                if not (0<=xx<w and 0<=yy<h and t[0,0,yy,xx]):continue
                bx,by=xx//b-x//b,yy//b-y//b
                if bx or by:out[0,5+DIRECTIONS.index((bx,by)),y//b,x//b]+=1/(1 if bx and by else 3*b-2)
    return out

def main():
    torch.set_num_threads(1);torch.manual_seed(19)
    for h,w in [(7,9),(8,8),(1,1),(5,3)]:
        z=torch.randint(0,3,(h,w));t=torch.stack([z==1,z==2,torch.zeros_like(z).bool()])[None].byte()*255
        for b in [2,4]:
            actual=count_map(t,b,True);assert torch.allclose(actual,expected(t,b),atol=1e-6)
            assert torch.equal(actual[:,:5],count_map(t,b))
    t=torch.zeros(1,3,8,8,dtype=torch.uint8);t[:,0]=255
    assert torch.equal(count_map(t,4,True)[:,5:9,0,0],torch.tensor([[0.,1.,1.,0.]]))
    # Test all eight transformations on blocks aligned with array boundaries.
    z=torch.randint(0,3,(8,8));t=torch.stack([z==1,z==2,torch.zeros_like(z).bool()])[None].byte()*255
    for b in [2,4]:
        baseline=count_map(t,b,True)
        for group in range(8):
            transformed=t.flip(-1) if group>=4 else t;transformed=torch.rot90(transformed,group%4,(-2,-1));target=baseline.flip(-1) if group>=4 else baseline;target=torch.rot90(target,group%4,(-2,-1))
            permutation=[]
            for dx,dy in DIRECTIONS:
                if group>=4:dx=-dx
                for _ in range(group%4):dx,dy=dy,-dx
                permutation.append(DIRECTIONS.index((dx,dy)))
            expected_channels=target.clone();expected_channels[:,[5+x for x in permutation]]=target[:,5:]
            assert torch.allclose(count_map(transformed,b,True),expected_channels,atol=1e-6)
    for kind in ['counts2','count_edges']:
        m=CompactPolicy(kind)
        for h,w in [(32,32),(70,80)]:
            g=torch.zeros(2,11,h,w,dtype=torch.uint8);g[:,0,1:-1,1:-1]=255;g[:,3]=255;stats=torch.tensor([[1.,.1,10.,10.],[1.,.1,0.,0.]]);mask=torch.ones(2,19);cache=ExactCache(m)
            with torch.no_grad():
                assert torch.allclose(m(g,mask,stats),cache(g,mask,stats),atol=1e-6)
                stats[:,2]+=1;cache(g,mask,stats);assert cache.refreshes==2
                g[0,4,4,4]=255;assert torch.allclose(m(g,mask,stats),cache(g,mask,stats),atol=1e-6);assert cache.refreshes==3
            m(g,mask,stats).square().mean().backward();assert all(torch.isfinite(p.grad).all() for p in m.parameters() if p.grad is not None)
        print('PASS',kind)
    print('PASS independent counts/crossings, padding, all rotations/reflections, rectangular shapes, caching and gradients')
if __name__=='__main__':main()
