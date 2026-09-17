"""Cache correctness checks independent of learned navigation quality."""
import torch
from cached_policy import CachedMapPolicy,FeatureCache

def main():
    torch.set_num_threads(1);torch.manual_seed(31)
    m=CachedMapPolicy();g=torch.zeros(2,11,32,32,dtype=torch.uint8);g[:,0,10:22,10:22]=255;g[:,3]=255;g[:,5,16,16]=255
    s=torch.tensor([[1.,.1,16.,16.]]).repeat(2,1);mask=torch.ones(2,19)
    with torch.no_grad():
        # Integer gathers must match nearest sampling, including map edges.
        from torch.nn import functional as F
        fmap=torch.randn(2,16,32,32);ss=s.clone();ss[:,2:4]=torch.tensor([[0.,0.],[31.,31.]])
        local,features,_=m.inputs(g,ss,fmap)
        expected=F.grid_sample(fmap,(m.read_xy+ss[:,None,None,2:4])/31*2-1,mode='nearest',align_corners=True).flatten(1)
        assert torch.equal(features,expected)
        c=FeatureCache(m,interval=1)
        assert torch.allclose(c(g,mask,s),m(g,mask,s),atol=1e-6)
        changed=g.clone();changed[:,2]=255;changed[:,3]=0;changed[:,5]=0;changed[:,6:]=17
        assert torch.equal(m.encoder(m.terrain(g)),m.encoder(m.terrain(changed)))
        s[:,2]+=1;c(g,mask,s);assert c.refreshes==2
        # Substantial discoveries and stairs refresh immediately, even at interval 8.
        c=FeatureCache(m,interval=8);c(g,mask,s);g[:,4,12,12]=255;c(g,mask,s);assert c.refreshes==4
        g[:,0,0,:16]=255;c(g,mask,s);assert c.refreshes==6
        g[:,0,1,0]=255
        for _ in range(7):c(g,mask,s)
        assert c.refreshes==6
        c(g,mask,s);assert c.refreshes==8
        c.reset_cache();assert c.snapshot is None
        assert torch.allclose(c(g,mask,s),m(g,mask,s),atol=1e-6)
        local,features,scalars=c.prepare(g,s)
    m.encoder.requires_grad_(False);before={k:v.clone() for k,v in m.encoder.state_dict().items()}
    opt=torch.optim.Adam(m.actor.parameters(),lr=1e-3);logits,value=m.actor(local,features,scalars,mask);loss=logits.square().mean()+value.square().mean();loss.backward();opt.step()
    assert all(torch.equal(v,before[k]) for k,v in m.encoder.state_dict().items())
    assert m.actor.policy.weight.grad.abs().sum()>0
    print('PASS: player-independent map, interval-1 equivalence, unchanged-map reuse, stair/discovery/interval refresh, reset isolation, frozen encoder with actor gradients')
if __name__=='__main__':main()
