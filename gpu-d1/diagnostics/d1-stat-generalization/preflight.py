"""Semantic, compatibility, CPU/CUDA, split, and information-boundary checks."""
import ctypes as C
import json
import time
import torch
import runtime as r
from learn_env_ring_multi import Env as OldEnv
from tactical_models import Policy as OldPolicy

@torch.no_grad()
def main():
    torch.set_num_threads(1);r.build();started=time.monotonic();report={}
    specs=r.SPEC['profiles'];axis=[i for i in r.SPEC['panels']['main'] if sum(x!=1 for x in specs[i]['code'])<=1]
    cases=axis+r.SPEC['panels']['extrapolation']
    # CPU and CUDA receive the same profile, placement, game RNG and legal actions.
    cpu=r.Env(assignments=cases,seed=471,device='cpu',map_limit=2,clump=0,balanced=True)
    gpu=r.Env(assignments=cases,seed=471,map_limit=2,clump=0,balanced=True)
    for step in range(128):
        assert torch.equal(cpu.obs,gpu.obs.cpu()),('obs',step)
        assert torch.equal(cpu.mask,gpu.mask.cpu()),('mask',step)
        a=cpu.heuristic().clone();cpu.step(a);gpu.step(a.cuda())
        assert torch.equal(cpu.out,gpu.out.cpu()),('out',step)
    report['cpu_cuda_decisions']=128*len(cases)
    # CPU semantics for each training one-factor and extrapolation setting.
    for case in cases:
        e=r.Env(assignments=[case],seed=411,device='cpu',map_limit=2,clump=0)
        e.check(e.lib.stats_semantics(C.byref(e.config),C.byref(e.tables)))
    report['semantic_profiles']=len(cases)
    print('PASS CPU/CUDA and variable-stat semantics',flush=True)
    # New episode spawning preserves map/player/stairs/deck across stat cells.
    e=r.Env(assignments=[i for i in cases for _ in range(8)],seed=871,seed_period=8,map_limit=2,clump=0,balanced=True)
    z=e.metadata_tensor().cpu().reshape(len(cases),8,18)
    assert (z[:,:,5:10]==z[0:1,:,5:10]).all()
    assert (z[:,:,12]==z[:,:,1]).all()
    assert (z[:,:,2]==z[:,:,3]).all()
    report['paired_geometry_profiles']=len(cases)
    # The new spawn protocol is distinct; compatibility uses identical saved states.
    old=OldEnv(16,24,seed=781,corpus=r.CORPUS/'train',map_limit=2,library_path=r.ROOT/'learning-runs/d1-stairs-assets/stairs-clump0.so')
    new=r.Env(batch=16,seed=781,map_limit=2,clump=0)
    offset=new.lib.stats_legacy_offset();assert new.state.shape[1]-offset==old.state.shape[1],(offset,new.state.shape,old.state.shape)
    new.state[:,offset:].copy_(old.state);new.observe()
    torch.testing.assert_close(new.obs,r.nominal_obs(old.obs),atol=0,rtol=0)
    active=torch.ones(16,device='cuda',dtype=torch.bool);paired=0
    for step in range(128):
        assert torch.equal(new.obs[active,:1015],old.obs[active]);assert torch.equal(new.mask[active],old.mask[active])
        a=old.heuristic().clone();old.step(a,active=active);new.step(a,active=active)
        assert torch.equal(new.out[active,:45],old.out[active]),('legacy outcome',step)
        paired+=int(active.sum());active &= ~old.out[:,1].bool()
    report['legacy_identical_state_decisions']=paired
    source=OldPolicy().cuda();source.load_state_dict(torch.load(r.SOURCE,map_location='cpu',weights_only=False)['model']);model=r.load_model()
    p,v=source(old.obs,old.mask);q,w=model(r.nominal_obs(old.obs),old.mask)
    torch.testing.assert_close(p.probs,q.probs,atol=3e-6,rtol=3e-5);torch.testing.assert_close(v,w,atol=3e-6,rtol=3e-5)
    # Nonzero new-field weights ensure the D4 check actually tests the new inputs.
    model.body[0].weight[:,1015:].normal_(0,.01)
    for group in range(8):
        g=torch.full((len(e.obs),),group,device='cuda');d=r.D4('cuda')
        order=torch.cat((d.forward[group,:8],d.forward[group,:8]+8,torch.tensor([16,17,18],device='cuda')))
        mask=torch.zeros_like(e.mask);mask[:,order]=e.mask
        p,v=model(e.obs,e.mask);q,w=model(d.observation(e.obs,g),mask)
        torch.testing.assert_close(p.probs,q.probs[:,order],atol=3e-6,rtol=3e-5);torch.testing.assert_close(v,w,atol=3e-6,rtol=3e-5)
    report['source_policy_preserved']=report['d4_covariance']=True
    # State snapshots include both stats and independent RNG streams.
    snap={k:getattr(e,k).clone() for k in ['state','obs','mask']};a=e.heuristic().clone();e.step(a)
    expected={k:getattr(e,k).clone() for k in ['state','obs','mask','out']}
    for k,v in snap.items():getattr(e,k).copy_(v)
    e.step(a)
    for k,v in expected.items():assert torch.equal(getattr(e,k),v),k
    varied=r.Env(batch=4096,seed=878,varied=True,map_limit=8,clump=1)
    meta=varied.metadata_tensor().cpu();hist=torch.bincount(meta[:,0],minlength=195)
    assert hist[0]/len(meta)>.20 and hist[0]/len(meta)<.30
    assert meta[:,0].max()<195 and (hist>0).all()
    report['sampling_nominal_fraction']=float(hist[0]/len(meta));report['sampled_train_profiles']=int((hist>0).sum())
    report['snapshot_restores_stats_rng']=True
    # Layout identity, not just file IDs, must be disjoint.
    import hashlib
    layouts={split:{hashlib.sha256(p.read_bytes()[28:5628]).hexdigest() for p in (r.CORPUS/split).glob('map-*.bin')} for split in ['train','validation','test']}
    assert not (layouts['train']&layouts['validation'] or layouts['train']&layouts['test'] or layouts['validation']&layouts['test'])
    report['layout_counts']={k:len(v) for k,v in layouts.items()}
    report['seconds']=time.monotonic()-started
    report['files']={str(p):r.digest(p) for p in [r.HERE/'runtime.py',r.HERE/'learn.cu',r.HERE/'hooks.cu',r.HERE/'preflight.py']}
    (r.SUITE/'preflight.json').write_text(json.dumps(report,indent=2)+'\n')
    (r.HERE/'profiles.json').write_text(json.dumps(r.SPEC,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
