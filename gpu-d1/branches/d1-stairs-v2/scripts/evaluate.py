"""D1 exit success with discovery, post-discovery and enemy-survival diagnostics."""
import torch
from common import env

@torch.no_grad()
def evaluate(model,split='validation',batch=1024,seed=950001,mode='sampled'):
    e=env(split,batch,seed);active=torch.ones(batch,device='cuda',dtype=torch.bool)
    terminal=torch.zeros_like(e.out);reward=torch.zeros(batch,device='cuda')
    counts=torch.zeros(batch,5,device='cuda');decisions=torch.zeros(batch,device='cuda')
    on_stairs=torch.zeros_like(decisions);departure=on_stairs.clone()
    with torch.random.fork_rng(devices=[0]):
        torch.manual_seed(seed)
        for _ in range(2048):
            if mode=='teacher':a=e.heuristic().clone()
            else:
                dist,_=model(e.obs,e.mask);a=dist.greedy() if mode=='greedy' else dist.sample()
            assert ((e.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all()
            kind=torch.where(a<8,0,torch.where(a<16,1,a-14))
            counts.scatter_add_(1,kind[:,None],active.float()[:,None]);decisions+=active
            on_stairs+=active*(e.mask[:,18]>0);departure+=active*(e.mask[:,18]>0)*(a<8)
            e.step(a,active=active);reward+=active*e.out[:,40]
            ended=active&(e.out[:,1]>0);terminal[ended]=e.out[ended];active&=~ended
            if not active.any():break
    assert not active.any()
    torch.testing.assert_close(reward,terminal[:,2]-.00001*terminal[:,5],atol=1e-4,rtol=0)
    t=terminal.cpu();r=reward.cpu();found=t[:,43]>=0;success=t[:,2]>0
    def mean(x,sel=None):
        if sel is not None:x=x[sel]
        return float(x.float().mean()) if len(x) else None
    assert ((t[:,2]+t[:,6]+t[:,7])==1).all()
    assert (t[success,44]>0).all()
    return dict(split=split,seed=seed,mode=mode,episodes=batch,exit_rate=mean(t[:,2]),death_rate=mean(t[:,6]),timeout_rate=mean(t[:,7]),
        turns=mean(t[:,5]),return_mean=mean(r),discovery_rate=mean(found),first_discovery_turn=mean(t[:,43],found),
        discovered_exit_rate=mean(t[:,2],found),post_discovery_turns_to_exit=mean(t[:,5]-t[:,43],success),
        deaths_before_discovery=int(((t[:,6]>0)&~found).sum()),deaths_after_discovery=int(((t[:,6]>0)&found).sum()),
        timeouts_before_discovery=int(((t[:,7]>0)&~found).sum()),timeouts_after_discovery=int(((t[:,7]>0)&found).sum()),
        kills=mean(t[:,3]),kills_on_exit=mean(t[:,3],success),enemies_alive_on_exit=mean(24-t[:,3],success),
        policy_decisions=mean(decisions.cpu()),on_stair_decisions=mean(on_stairs.cpu()),moves_off_stairs=mean(departure.cpu()),
        actions={k:mean(counts[:,i].cpu()) for i,k in enumerate(['move','attack','wait','rest','descend'])},
        maps=[int(m['seed']) for m in e.metadata],
        outcomes={k:t[:,col].tolist() for k,col in [('exit',2),('death',6),('timeout',7),('turns',5),('kills',3),('first_discovery',43)]})
