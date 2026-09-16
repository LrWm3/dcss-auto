"""Architecture guarantees, curriculum transitions/resume, and legacy initialization."""
import json
import pathlib
import torch
from assets import ROOT,ASSETS
from tactical_models import Policy
from symmetry import D4
from tactical_env import TacticalEnv,MixedEnv
from learn_env_ring_multi import Env
from prepare import source,library

def main():
    torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
    suite,name=source(0,'clumped');manifest=json.loads((suite/'manifest.json').read_text());old=manifest['jobs'][0]
    corpus=pathlib.Path(manifest['corpus'])
    lib=library(suite,dict(old,clump_mode=0))
    base=Env(64,24,seed=170,corpus=corpus/'validation',map_limit=4,library_path=lib)
    tactical=TacticalEnv(64,24,seed=170,corpus=ASSETS/'train',map_limit=64,map_filter=-2,library_path=ASSETS/'tactical.so')
    assert (tactical.obs[:,650]>=6/18).all() and (tactical.obs[:,650]<=1).all()
    # Raw scenario enemy positions may be occluded but never exceed constructed count.
    assert (tactical.obs[:,225:450].gt(0).sum(1)<=6).all()
    for item in tactical.metadata:
        s=json.loads((ASSETS/'train/scenarios.json').read_text())[item['seed']]
        floor={tuple(x) for x in s['floor']};goal=tuple(s['goal'])
        assert sum((goal[0]+x,goal[1]+y) in floor for x in [-1,0,1] for y in [-1,0,1] if x or y)==1
    mixed=MixedEnv(base,tactical,71);torch.manual_seed(91)
    for step in range(512):
        before=mixed.is_tactical.clone();action=torch.distributions.Categorical(probs=mixed.mask).sample()
        if step==128:
            state=mixed.state.clone();snap=mixed.snapshot();rng=torch.cuda.get_rng_state()
            mixed.step(action);after=[mixed.state.clone(),mixed.obs.clone(),mixed.mask.clone(),mixed.out.clone(),mixed.is_tactical.clone(),mixed.counts.clone()]
            mixed.state.copy_(state);mixed.restore(snap);torch.cuda.set_rng_state(rng)
            mixed.step(action)
            assert all(torch.equal(a,b) for a,b in zip(after,[mixed.state,mixed.obs,mixed.mask,mixed.out,mixed.is_tactical,mixed.counts]))
        else:mixed.step(action)
        live=mixed.out[:,1]==0;assert torch.equal(before[live],mixed.is_tactical[live])
    assert mixed.counts[1]>0 and mixed.counts[3]>0
    # Test exact architecture properties on actual and deliberately non-symmetric inputs.
    o=base.obs[:16].clone();o[:,450:650]=torch.randn(16,200,device='cuda');mask=torch.ones(16,9,device='cuda')
    for architecture in ['mlp','enemy_set','d4_exact']:
        torch.manual_seed(0);model=Policy(architecture).cuda();p,v=model(o,mask)
        if architecture=='mlp':
            initial=torch.load(ROOT/'learning-runs/vision15-clumps-30m/runs/clumps_third-seed0/snapshots/000000000000.pt',weights_only=False,map_location='cpu')['model']
            assert all(torch.equal(t.cpu(),initial[k]) for k,t in model.state_dict().items())
        elif architecture=='enemy_set':
            permuted=o.clone();permuted[:,450:650]=o[:,450:650].reshape(16,40,5)[:,torch.arange(39,-1,-1),:].flatten(1)
            q,w=model(permuted,mask);torch.testing.assert_close(p.probs,q.probs,atol=2e-6,rtol=2e-5);torch.testing.assert_close(v,w,atol=2e-6,rtol=2e-5)
        else:
            d=D4()
            for g in range(8):
                groups=torch.full((16,),g,device='cuda',dtype=torch.long);q,w=model(d.observation(o,groups),d.mask(mask,groups))
                torch.testing.assert_close(p.probs,q.probs.gather(1,d.forward[groups]),atol=2e-6,rtol=2e-5);torch.testing.assert_close(v,w,atol=2e-6,rtol=2e-5)
        loss=p.log_prob(torch.zeros(16,dtype=torch.long,device='cuda')).mean()+v.square().mean();loss.backward()
        assert all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None)
    r=dict(legacy_initial_weights_exact=True,enemy_set_permutation_invariant=True,d4_actor_equivariant_and_critic_invariant=True,all_architecture_gradients_finite=True,curriculum_episode_switching_and_resume_exact=True,curriculum_counts=mixed.counts.cpu().tolist(),geometry_disjoint=json.loads((ASSETS/'geometry-checks.json').read_text())['layout_disjoint'])
    (ROOT/'results/tactical-next-preflight.json').write_text(json.dumps(r,indent=2)+'\n');print(r)
if __name__=='__main__':main()
