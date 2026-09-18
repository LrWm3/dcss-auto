"""Independent map aggregation and recurrent/replay correctness checks."""
import time,torch
from symbolic_run import Sequences,collect
from symbolic_policy import categories,global_map,SymbolicPolicy,Stateful
from runtime import Env,build

def main():
    torch.set_num_threads(1);torch.manual_seed(13);build()
    for h,w in [(32,32),(70,80)]:
        z=torch.randint(0,4,(2,h,w));g=torch.zeros(2,11,h,w,dtype=torch.uint8)
        g[:,0]=((z==2)|(z==3)).byte()*255;g[:,1]=(z==1).byte()*255;g[:,2]=(z==3).byte()*255;g[:,4,5,7]=255
        s=torch.tensor([[1.,.1,7.,5.]]).repeat(2,1);c=categories(g)
        assert torch.equal(c.sum(1),torch.ones_like(c[:,0]))
        assert torch.equal(c.argmax(1),z)
        out=global_map(g,s);expected=torch.zeros_like(out);counts=torch.zeros(16,16)
        for y in range(h):
            for x in range(w):
                by,bx=y*16//h,x*16//w;counts[by,bx]+=1;expected[:,:4,by,bx]+=c[:,:,y,x]
        expected[:,:4]/=counts.clamp_min(1);expected[:,4,5*16//h,7*16//w]=1;expected[:,5,5*16//h,7*16//w]=1
        assert torch.equal(out,expected)
        old=out.clone();g[:,6:]=255;g[:,3]=255;assert torch.equal(old,global_map(g,s))
        for recurrent in [False,True]:
            m=SymbolicPolicy(recurrent);mask=torch.ones(2,19);logits=m(g,mask,s);assert logits.shape==(2,19);assert torch.isfinite(logits).all()
    e=Env(batch=8);buffer=Sequences(capacity=64);collect(e,buffer,steps=35)
    # Partial chunks preserve time order and mask padding out of losses.
    for j in range(buffer.n):
        valid=buffer.v[j];times=buffer.s[j,valid,1];assert (times[1:]>=times[:-1]).all()
        assert buffer.v[j,16:].any()
    for recurrent in [False,True]:
        m=SymbolicPolicy(recurrent).cuda();opt=torch.optim.Adam(m.parameters(),lr=.0003)
        e.reset(seed=11);state=Stateful(m);a=state(e.grid,e.mask,e.stats);state(e.grid,e.mask,e.stats);state.reset_cache();b=state(e.grid,e.mask,e.stats);assert torch.equal(a,b)
        if recurrent:
            x=m.encode(e.grid,e.stats);h=torch.zeros(8,128,device='cuda');outs=[]
            for _ in range(3):z,h=m.step_features(x,e.mask,h);outs.append(z)
            state.reset_cache()
            for z in outs:assert torch.allclose(z,state(e.grid,e.mask,e.stats),atol=1e-6)
            # Prior state influences logits and gradients pass through time.
            assert not torch.allclose(outs[0],outs[2]);assert torch.autograd.grad(outs[2].sum(),x,retain_graph=True)[0].abs().sum()>0
        torch.cuda.synchronize();start=time.monotonic()
        for _ in range(20):
            opt.zero_grad(set_to_none=True);loss,n=buffer.loss(m);assert n>0 and torch.isfinite(loss);loss.backward();assert all(torch.isfinite(p.grad).all() for p in m.parameters() if p.grad is not None);opt.step()
        torch.cuda.synchronize();print('PASS', 'gru' if recurrent else 'ff','20 single-buffer updates seconds',time.monotonic()-start,flush=True)
    print('PASS categories, disjoint full-map bins, stairs, player marker, tactical isolation, rectangular inputs, replay order, state reset and gradients')
if __name__=='__main__':main()
