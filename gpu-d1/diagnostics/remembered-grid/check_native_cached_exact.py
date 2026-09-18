"""Cache parity, observed-data contract, gradients, and trajectory replay timing."""
import time
import torch
from run import save_json
from native_cached_exact import make_model,CachedInference
from native_remedies import make_model as base_model,ExactPolicy
from native_curriculum import factory
from fullsize_navigation import build_full
from runtime import ROOT


def main():
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True;build_full()
    model=make_model();base=base_model();env=factory(1)('validation',32);env.reset(seed=71)
    with torch.no_grad():
        torch.testing.assert_close(model.encode(env.grid,env.stats),base.encode(env.grid,env.stats),rtol=1e-5,atol=1e-6)
        # Known terrain and stairs only; player location is read separately.
        p=model.prepare(env.grid,env.stats);assert (p[1][:,:4].sum(1)==1).all()
        for a,b in zip(p,ExactPolicy.prepare(model,env.grid,env.stats)):
            assert torch.equal(a,b)
        packed=torch.nn.functional.pixel_unshuffle(p[1][:,:5],2)
        assert torch.equal(torch.nn.functional.pixel_shuffle(packed,2),p[1][:,:5])
        # Activate the new branch before checking cache parity.
        model.map_readout[-1].weight.normal_(0,.02)
    cached=CachedInference(model);uncached=CachedInference(model,False)
    trajectory=[];worst=0.;disagreements=0
    for t in range(96):
        g,m,s=env.grid.clone(),env.mask.clone(),env.stats.clone();trajectory.append((g,m,s))
        a=cached(g,m,s);b=uncached(g,m,s)
        torch.testing.assert_close(a,b,atol=.006,rtol=.003)
        worst=max(worst,float((a-b).abs().max()));disagreements+=int((a.argmax(1)!=b.argmax(1)).sum())
        env.step(env.labels.clone(),limit=1024)
    refresh_fraction=cached.refreshes/cached.observations
    # Identical map / changed player: reuse terrain encoding, update readout.
    cached.reset_cache();g,m,s=trajectory[0];cached(g,m,s);before=cached.refreshes
    g2=g.clone();g2[:,5].zero_();s2=s.clone();s2[:,2]=(s2[:,2]+1).clamp(max=79)
    g2[:,5].flatten(1).scatter_(1,(s2[:,3].long()*80+s2[:,2].long())[:,None],255)
    cached(g2,m,s2);assert cached.refreshes==before
    # Any map-encoder update must invalidate every cached slot.
    with torch.no_grad():next(model.map_encoder.parameters()).add_(1e-5)
    cached(g2,m,s2);assert cached.refreshes==before+len(g)
    cached.reset_cache();assert cached.snapshot is None and cached.hidden is None
    model.zero_grad(set_to_none=True)
    x=model.encode(env.grid,env.stats);loss=x.square().mean();loss.backward()
    grad=sum(float(p.grad.abs().sum()) for p in model.map_encoder.parameters() if p.grad is not None)
    assert grad>0 and torch.isfinite(loss)
    timings={}
    for name,policy in [('uncached',uncached),('cached',cached)]:
        policy.reset_cache();policy(*trajectory[0]);torch.cuda.synchronize();start=time.monotonic()
        for _ in range(2):
            policy.reset_cache()
            for args in trajectory:policy(*args)
        torch.cuda.synchronize();elapsed=time.monotonic()-start
        timings[name]=dict(seconds=elapsed,decisions_per_second=2*len(trajectory)*32/elapsed)
    report=dict(passed=True,initial_source_parity=True,lossless_space_to_depth=True,cache_max_logit_error=worst,greedy_disagreements=disagreements,trajectory_refresh_fraction=refresh_fraction,position_only_reuses_cache=True,weight_update_invalidates=True,encoder_gradient_l1=grad,batch=32,map_shape=[70,80],timing_scope='Eager AMP policy-only teacher-trajectory replay, includes preprocessing and cache checks; excludes environment and gradient updates. Not PPO throughput.',timings=timings)
    save_json(ROOT/'results/native-cached-exact-check.json',report);print(report,flush=True)

if __name__=='__main__':main()
