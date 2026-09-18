"""Check raw-buffer parity, fresh-weight replay and optimizer integration."""
import torch
from native_remedies import Buffer, make_model
from native_curriculum import factory, collect
from native_history_replay import HistoryBuffer, collect_history
from symbolic_execution import PolicyExecution, StaticInference
from run import save_json
from runtime import ROOT
from fullsize_navigation import build_full


def main():
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True;build_full()
    model=make_model();execution=PolicyExecution(model,compiled=True)
    policy=StaticInference(execution,amp=True,graphed=True);env=factory(1)('train',32)
    old=Buffer(balanced=True);new=HistoryBuffer(balanced=True,full=False)
    torch.manual_seed(774);a=collect(env,old,model,policy,0,1999)
    torch.manual_seed(774);b=collect_history(env,new,model,policy,0,1999)
    assert a==b and old.n==len(new.entries)
    # Compare every retained learning chunk, including ring order and padding.
    for i,(v,w,start) in enumerate(new.entries):
        for j,p in enumerate(old.p+[old.mask,old.label,old.valid]):
            torch.testing.assert_close(p[i,16:],v[j][w,start:start+16],rtol=0,atol=0)
    for key in ['collected','retained','sequences']:
        assert old.coverage()[key]==new.coverage()[key]
    torch.manual_seed(314);oldloss,_=old.loss(model,execution)
    torch.manual_seed(314);newloss,_=new.loss(model,execution)
    torch.testing.assert_close(oldloss,newloss,rtol=.002,atol=.002)
    report=dict(decisions=a,retained_chunks=old.n,buffer_parity=True,
                short_loss_old=float(oldloss),short_loss_new=float(newloss),checks=[])
    del oldloss,newloss,old
    # Deep prefixes, first chunk, and partial terminal chunks from actual data.
    entries=[next(e for e in new.entries if e[2]==start) for start in sorted(set(e[2] for e in new.entries))[::4]]
    entries.append(next(e for e in new.entries if not e[0][6][e[1],e[2]:e[2]+16].all()))
    new.full=True
    def compare(label):
        with torch.no_grad():
            logits,_,valid,_=new.logits(entries,model,execution)
            maximum=0.;disagree=0;states=0
            for i,(v,w,start) in enumerate(entries):
                h=torch.zeros(1,128,device='cuda');live=[]
                with torch.autocast('cuda',dtype=torch.float16):
                    x=model.encode_prepared([p[w,:start+16] for p in v[:4]])
                    for tick in range(start+16):
                        h=model.core(x[tick:tick+1],h)
                        if tick>=start:
                            live.append(model.policy(h).float().masked_fill(v[4][w,tick:tick+1]==0,-1e9)[0])
                actual=torch.stack(live)
                p=torch.distributions.Categorical(logits=actual,validate_args=False)
                q=torch.distributions.Categorical(logits=logits[i],validate_args=False)
                kl=torch.distributions.kl_divergence(p,q)[valid[i]]
                maximum=max(maximum,float(kl.max()))
                disagree+=int(((actual.argmax(-1)!=logits[i].argmax(-1))&valid[i]).sum())
                states+=int(valid[i].sum())
            assert maximum<1e-4,(label,maximum)
            report['checks'].append(dict(label=label,max_kl=maximum,action_disagreements=disagree,states=states))
    compare('initial_weights')
    assert not new.reconstruct(entries,model,execution).requires_grad
    opt=torch.optim.Adam(model.parameters(),lr=1e-4);scaler=torch.amp.GradScaler('cuda',init_scale=1024)
    before=model.core.weight_ih.detach().clone()
    opt.zero_grad(set_to_none=True);loss,_=new.loss(model,execution)
    scaler.scale(loss).backward();scaler.unscale_(opt)
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters())
    assert model.local[0].weight.grad.abs().sum()>0
    torch.nn.utils.clip_grad_norm_(model.parameters(),1);scaler.step(opt);scaler.update()
    assert not torch.equal(before,model.core.weight_ih)
    compare('after_optimizer_update')
    report['prefix_detached']=True;report['encoder_and_recurrent_update']=True
    save_json(ROOT/'results/native-history-check.json',report);print(report,flush=True)

if __name__=='__main__':main()
