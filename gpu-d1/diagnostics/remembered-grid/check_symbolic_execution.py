"""Live-data graph replay, encoder gradients, optimizer and recurrent reset checks."""
import argparse
import torch
from symbolic_execution import StaticUpdate,StaticInference
from optimize_symbolic import inputs


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--compiled',action='store_true');args=ap.parse_args()
    torch.set_num_threads(1);torch.backends.cudnn.benchmark=True
    for amp in (False,True):
        torch.manual_seed(193);ref=StaticUpdate(32,amp,prepared=True)
        torch.manual_seed(193);opt=StaticUpdate(32,amp,prepared=True,compiled=args.compiled,graphed=True)
        for tick in range(4):
            # Same changing data, not repeated inference on frozen capture inputs.
            for u in (ref,opt):
                u.ret.fill_(.1*tick);u.adv.fill_(.2+.05*tick);u.action.fill_(tick)
                u.p[0][:,:,3:5,3:5]=tick*.1
                u.pb[1][:,:,2:4,2:4]=tick*.2
                u.step()
            atol=5e-4 if amp else 2e-5
            torch.testing.assert_close(opt.current_loss,ref.current_loss,atol=atol,rtol=atol)
            for (name,p),(oname,q) in zip(ref.model.named_parameters(),opt.model.named_parameters()):
                assert name==oname and p.grad is not None and q.grad is not None
                assert torch.isfinite(q.grad).all(),name
                torch.testing.assert_close(p.grad,q.grad,atol=atol,rtol=atol)
                torch.testing.assert_close(p,q,atol=atol,rtol=atol)
        if amp:
            # Overflow handling stays live outside capture; subsequent replays
            # must see the updated scale and overwrite the nonfinite gradients.
            saved=[p.detach().clone() for p in opt.model.parameters()]
            scale=opt.scaler.get_scale()
            for u in (ref,opt):u.ret.fill_(float('inf'));u.step()
            assert opt.scaler.get_scale()<scale
            for p,q in zip(saved,opt.model.parameters()):torch.testing.assert_close(p,q,rtol=0,atol=0)
            for u in (ref,opt):u.ret.fill_(.2);u.step()
            for p,q in zip(ref.model.parameters(),opt.model.parameters()):
                assert torch.isfinite(q.grad).all()
                torch.testing.assert_close(p,q,atol=atol,rtol=atol)
            print('PASS overflow skips update, lowers scale, and recovers on next replay',flush=True)
        print('PASS training',dict(amp=amp,compiled=args.compiled),'4 live-input updates, all gradients and weights',flush=True)
        # Reuse identical weights after testing numerically close optimizer paths.
        opt.model.load_state_dict(ref.model.state_dict())
        a=StaticInference(ref.execution,amp,False);b=StaticInference(opt.execution,amp,True)
        g,mask,s=inputs(16)
        for tick in range(8):
            if tick in (0,4):a.reset_cache();b.reset_cache()
            s[:,0]=1-tick*.05;g[:,2,:,tick]=255
            mask.fill_(1);mask[:,tick]=0
            with torch.no_grad():la,va=a.outputs(g,mask,s);lb,vb=b.outputs(g,mask,s)
            torch.testing.assert_close(la,lb,atol=atol,rtol=atol)
            torch.testing.assert_close(va,vb,atol=atol,rtol=atol)
            assert (lb[:,tick]==-1e9).all()
        print('PASS inference changing observations/masks/stats, carried state and episode resets',flush=True)

if __name__=='__main__':main()
