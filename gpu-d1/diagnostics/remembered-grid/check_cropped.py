"""Validate cropped decoder outputs and training gradients against full decoder."""
import torch,json
from runtime import CroppedSpatialPolicy,OUT
from performance import FullSpatial

def main():
    torch.manual_seed(431);torch.set_num_threads(1);rows=[]
    tie=torch.ones(1,2,5,7,requires_grad=True);pool=CroppedSpatialPolicy(amp=False);pool.fast_pool=True
    pool.pool(tie).sum().backward();actual=tie.grad.clone();tie.grad=None
    torch.nn.functional.max_pool2d(tie,2).sum().backward();assert torch.equal(actual,tie.grad)
    for h,w in [(32,32),(70,80),(31,37)]:
        positions=[[0,0],[w-1,0],[0,h-1],[w-1,h-1],[1,2],[w-2,h-2],[w//2,h//2],[3,4]];n=len(positions)
        g=torch.randint(256,(n,11,h,w),device='cuda',dtype=torch.uint8);s=torch.tensor([[1.,.1,*p] for p in positions],device='cuda');mask=torch.ones(n,19,device='cuda')
        reference=FullSpatial(False).cuda();cropped=CroppedSpatialPolicy('terrain',False).cuda();cropped.load_state_dict(reference.state_dict());cropped.fast_pool=True
        a=reference(g,mask,s);b=cropped(g,mask,s);torch.testing.assert_close(a,b,rtol=2e-5,atol=2e-6)
        target=torch.arange(n,device='cuda')%19;torch.nn.functional.cross_entropy(a,target).backward();torch.nn.functional.cross_entropy(b,target).backward();maxgrad=0.
        for (name,p),(other,q) in zip(reference.named_parameters(),cropped.named_parameters()):
            assert name==other
            torch.testing.assert_close(p.grad,q.grad,rtol=2e-3,atol=2e-6,msg=name);maxgrad=max(maxgrad,float((p.grad-q.grad).abs().max()))
        cropped.amp=True;cropped.to(memory_format=torch.channels_last);c=cropped(g,mask,s);torch.testing.assert_close(a,c,rtol=.02,atol=.002)
        rows.append(dict(shape=[h,w],positions=n,max_logit_error=float((a-b).abs().max()),max_gradient_error=maxgrad,max_amp_logit_error=float((a-c).abs().max())))
    report=dict(passed=True,pool_tie_gradients_match=True,rows=rows);(OUT/'cropped-checks.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()
