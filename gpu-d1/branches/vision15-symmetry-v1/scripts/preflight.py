"""Independent feature, action, native trajectory and resume checks."""
import json
import pathlib
import torch
import run_ring_ablations as runner
from learn_env_ring_multi import Env
from symmetry import D4, EpisodeSymmetry

def reference(o,g):
    # Independent matrix/coordinate implementation, deliberately no D4 lookup tables.
    import numpy as np
    m = np.array([[-1,0],[0,1]]) if g>=4 else np.eye(2,dtype=int)
    for _ in range(g%4):m=np.array([[0,-1],[1,0]])@m
    out=o.copy()
    for start in [0,225,733]:
        for y in range(-7,8):
            for x in range(-7,8):
                xx,yy=m@np.array([x,y]);out[start+(yy+7)*15+xx+7]=o[start+(y+7)*15+x+7]
    ring=[(x,y) for y in [-8,8] for x in range(-8,9)]+[(x,y) for x in [-8,8] for y in range(-7,8)]
    for j,(x,y) in enumerate(ring):out[654+ring.index(tuple(m@np.array([x,y])))]=o[654+j]
    for j,sx,sy,cx,cy in [(j,80,70,0,0) for j in range(450,650,5)]+[(719,80,70,0,0),(723,1,1,0,0),(652,80,70,39.5,34.5)]:
        p=m@(o[j:j+2]*[sx,sy]-[cx,cy])+[cx,cy];out[j:j+2]=p/[sx,sy]
    directions=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]
    for a,p in enumerate(directions):out[725+directions.index(tuple(m@p))]=o[725+a]
    return out

def main():
    import numpy as np
    torch.set_num_threads(1)
    root=runner.ROOT.parents[1]
    old=json.loads((root/'learning-runs/vision15-clumps-30m/manifest.json').read_text())
    job=dict(old['jobs'][0],clump_mode=0)
    store=runner.Store(root/'learning-runs/vision15-symmetry-preflight',2*runner.GIB,5*runner.GIB)
    store.root.mkdir(parents=True,exist_ok=True)
    lib=runner.build(store,job)
    kwargs=dict(batch=64,enemies=24,seed=900000,corpus=pathlib.Path(old['corpus'])/'validation',map_limit=4,map_filter=-2,library_path=lib)
    a=Env(**kwargs);raw=Env(**kwargs);b=EpisodeSymmetry(raw,seed=71)
    d=b.transform
    random=torch.randn(8,959,device='cuda');groups=torch.arange(8,device='cuda')
    for inputs in [random,a.obs[:8]]:
        expected=np.stack([reference(o,g) for g,o in enumerate(inputs.cpu().numpy())])
        np.testing.assert_allclose(d.observation(inputs,groups).cpu().numpy(),expected,rtol=1e-6,atol=1e-6)
        for g in range(8):
            inv=g if g>=4 else (-g)%4
            transformed=d.observation(inputs,torch.full_like(groups,g))
            torch.testing.assert_close(d.observation(transformed,torch.full_like(groups,inv)),inputs,rtol=1e-6,atol=1e-6)
    assert torch.equal(d.observation(a.obs,torch.zeros(64,dtype=torch.long,device='cuda')),a.obs)
    for g in range(8):
        p=d.forward[g];assert sorted(p.tolist())==list(range(9)) and int(p[8])==8
        for act in range(9):assert int(d.to_world(p[act:act+1],torch.tensor([g],device='cuda'))[0])==act
    torch.manual_seed(723)
    reset_count=0
    for step in range(256):
        old_groups=b.groups.clone()
        actions=torch.distributions.Categorical(probs=b.mask).sample()
        actual=d.to_world(actions,old_groups)
        assert a.mask.gather(1,actual[:,None]).bool().all()
        a.step(actual);b.step(actions)
        assert torch.equal(a.state,b.state) and torch.equal(a.out,b.out)
        assert torch.equal(a.obs,b.base.obs) and torch.equal(a.mask,b.base.mask)
        ended=b.out[:,1]>0;reset_count+=int(ended.sum())
        assert torch.equal(b.groups[~ended],old_groups[~ended])
        assert torch.equal(b.obs,d.observation(a.obs,b.groups))
        if step==100:
            native=b.state.clone();snapshot=b.snapshot()
            before_obs=b.obs.clone();before_mask=b.mask.clone()
            # Execute, restore, execute again: orientation RNG and native RNG both replay.
            action=torch.distributions.Categorical(probs=b.mask).sample()
            b.step(action);state1=b.state.clone();obs1=b.obs.clone();out1=b.out.clone();g1=b.groups.clone()
            b.state.copy_(native);b.restore(snapshot)
            assert torch.equal(before_obs,b.obs) and torch.equal(before_mask,b.mask)
            b.step(action)
            assert torch.equal(state1,b.state) and torch.equal(obs1,b.obs) and torch.equal(out1,b.out) and torch.equal(g1,b.groups)
            b.state.copy_(native);b.restore(snapshot)
    assert reset_count>0
    result=dict(independent_feature_reference=True,identity_exact=True,all_inverse_transforms=True,all_action_roundtrips=True,native_state_obs_mask_output_parity=True,worlds=64,steps=256,resets=reset_count,episode_orientation_stable=True,resume_replay_exact=True)
    (root/'results/vision15-symmetry-preflight.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result,flush=True)
if __name__=='__main__':main()
