"""Representation, shape, precision and baseline-adapter checks."""
import json,torch
from torch.nn import functional as F
from runtime import SpatialPolicy,PackedPolicy,OUT
from performance import FullSpatial

def main():
    torch.set_num_threads(1);torch.manual_seed(99)
    checked=[]
    for h,w in [(32,32),(70,80),(31,37)]:
        x=torch.randint(256,(2,11,h,w),dtype=torch.uint8)
        padded=F.pad(x,(0,(-w)%16,0,(-h)%16))
        assert torch.equal(F.pixel_shuffle(F.pixel_unshuffle(padded,4),4)[...,:h,:w],x)
        g=x.cuda();s=torch.tensor([[1.,.1,0.,0.],[.5,.2,w-1,h-1]],device='cuda');mask=torch.ones(2,19,device='cuda');mask[:,3]=0
        m=PackedPolicy('terrain',amp=False).cuda();a=m(g,mask,s)
        assert torch.isfinite(a).all() and (a[:,3]==-1e9).all()
        m.amp=True;m.to(memory_format=torch.channels_last);b=m(g,mask,s)
        err=float((a[:,[i for i in range(19) if i!=3]]-b[:,[i for i in range(19) if i!=3]]).abs().max());assert err<.01,err
        loss=F.cross_entropy(b,torch.zeros(2,device='cuda',dtype=torch.long));loss.backward();assert all(p.grad is None or torch.isfinite(p.grad).all() for p in m.parameters())
        checked.append(dict(shape=[h,w],amp_max_logit_difference=err))
    g=torch.randint(256,(4,11,32,32),device='cuda',dtype=torch.uint8);s=torch.tensor([[1.,.1,16.,16.]],device='cuda').repeat(4,1);mask=torch.ones(4,19,device='cuda')
    old=SpatialPolicy('terrain').cuda();adapter=FullSpatial().cuda();adapter.load_state_dict(old.state_dict())
    torch.testing.assert_close(old(g,mask,s),adapter(g,mask,s),rtol=1e-5,atol=1e-6)
    result=dict(packing_roundtrip=True,shapes=checked,baseline_adapter_matches=True,passed=True)
    (OUT/'packed-checks.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
