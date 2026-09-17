import ctypes as C
import json
import torch
import runtime as r

def main():
    torch.set_num_threads(1);r.build();report={}
    for split in ['train','validation','test']:
        e=r.Env(split,assignments=[i%9 for i in range(512)],seed=4181,varied=split=='train',clump=0)
        e.inject(initial=True,percent=100);sel=e.tags.bool();z=e.inspect()[sel.cpu()];n=int(sel.sum())
        assert n>0 and (z[:,11]>0).all() and (z[:,7]==1).all() and (z[:,10]>=0).all()
        assert (e.obs[sel,999]==0).all() and (e.obs[sel,450:650].reshape(-1,40,5)[:,:,4].sum(1)==1).all()
        assert (e.obs[sel,959:999]<0).sum()==0
        report[split]={'attempts':512,'accepted':n,'maps':len(z[:,6].unique())}
        if split in ['validation','test']:
            bank={k:getattr(e,k)[sel].cpu() for k in ['state','obs','mask']}
            bank['rows']=[{'state':i} for i in range(n)]
            # Policy rollout simulator must preserve the original world assignments.
            bank['assignments']=e.assignment_tensor.cpu();bank['seed']=4181
            torch.save(bank,r.SUITE/f'practice-{split}.pt')
        p=C.c_void_p;e.ext.bypass_verify.argtypes=[p,C.c_int,p,p,p,p,p]
        out=torch.zeros(e.batch,dtype=torch.int32,device='cuda')
        e.check(e.ext.bypass_verify(e.state.data_ptr(),e.batch,C.byref(e.config),C.byref(e.tables),e.tags.data_ptr(),out.data_ptr(),e.stream))
        assert int(out.sum())==n;report[split]['verified_no_wake_no_damage_exits']=n
    # Exercise autoreset curriculum integration and reward accounting.
    r.MIX=40;e=r.Env(batch=64,seed=111,varied=True);m=r.load_model()
    with torch.no_grad():
        for _ in range(128):
            a=m(e.obs,e.mask)[0].sample();e.step(a)
            torch.testing.assert_close(e.out[:,40],e.out[:,2]-.00001*e.out[:,26],atol=1e-6,rtol=0)
            assert torch.isfinite(e.obs).all() and (e.mask.sum(1)>0).all()
    report['mixed_completed']=e.completed.cpu().tolist();report['source_sha256']=r.digest(r.SOURCE)
    (r.SUITE/'preflight.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
