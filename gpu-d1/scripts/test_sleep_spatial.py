"""CPU/CUDA parity, observation semantics, unchanged ring-task transitions."""
import torch
from learn_env_sleep_spatial import Env
from train_sleep_spatial import Policy

def main():
    torch.set_num_threads(1)
    torch.manual_seed(73)
    cpu=Env(37,8,91,device='cpu'); gpu=Env(37,8,91)
    import learn_env_sleep
    learn_env_sleep._LIB=None
    learn_env_sleep.LIB_NAME='learn_sleep_explore_ring.so'
    ring=Env(37,8,91,device='cpu')
    for k in range(301):
        for name in ('obs','mask','state'):
            assert torch.equal(getattr(cpu,name),getattr(gpu,name).cpu()),(k,name)
        assert torch.equal(cpu.state,ring.state),(k,'ring state')
        assert torch.equal(cpu.obs[:,:206],ring.obs[:,:206]),(k,'base observation')
        maps=cpu.obs[:,206:].reshape(37,4,5600)
        assert torch.equal(maps[:,0],cpu.arrays[0].float().expand(37,-1))
        assert (maps[:,2].sum(1)==1).all()
        coords=cpu.obs[:,204:206]*torch.tensor([80.,70.])
        indices=coords.round().long()[:,1]*80+coords.round().long()[:,0]
        assert torch.equal(maps[:,2].argmax(1),indices)
        assert ((maps[:,1]==0)|(maps[:,0]>0)).all()
        assert torch.equal((maps[:,3]>0).sum(1),(cpu.obs[:,162:202].reshape(37,8,5)[:,:,4]>0).sum(1))
        actions=cpu.heuristic().clone() if k%2==0 else torch.randint(9,(37,))
        cpu.step(actions); gpu.step(actions.cuda()); ring.step(actions)
        assert torch.equal(cpu.out,gpu.out.cpu())
        assert torch.equal(cpu.out,ring.out),(k,'ring reward/terminal')
    model=Policy().cuda()
    dist,value=model(gpu.obs,gpu.mask)
    (value.mean()+dist.entropy().mean()).backward()
    assert all(torch.isfinite(p.grad).all() for p in model.parameters())
    print('PASS: 301 steps, 37 worlds; CPU/CUDA parity; ring transition/reward parity; map semantics; policy gradients')
if __name__=='__main__': main()
