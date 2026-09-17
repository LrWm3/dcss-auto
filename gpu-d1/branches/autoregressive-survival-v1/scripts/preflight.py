"""Meaningful checks for native practice resets, PPO probabilities and resume state."""
import importlib.util,json,pathlib,time
import torch
from tactical_env import TacticalEnv,MixedEnv
from tactical_models import Policy
from learn_env_ring_multi import Env
from survival_eval import evaluate_tactics
from scenarios import ROOT,ASSETS,FAMILIES
from run_ring_ablations import digest

SOURCE=ROOT/'learning-runs/autoregressive-anchor-navigation-30m'

def settings():
    old=json.loads((SOURCE/'manifest.json').read_text());job=dict(old['jobs'][0])
    job.update(tactical_library=str(ASSETS/'survival.so'),tactical_corpus=str(ASSETS/'train'),tactical_eval_corpus=str(ASSETS/'heldout'),practice_worlds=51,practice_temperature=5.)
    return old,job


def main():
    torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False;start=time.monotonic()
    manifest,job=settings();saved=torch.load(SOURCE/'runs/navigation1-seed0/latest.pt',map_location='cpu',weights_only=False)
    model=Policy('d4_exact',128).cuda().eval();model.load_state_dict(saved['model'])
    old_path=ROOT/'branches/autoregressive-turn-cost-v1/scripts/tactical_models.py'
    spec=importlib.util.spec_from_file_location('original_policy',old_path);oldmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(oldmod)
    original=oldmod.Policy('d4_exact',128).cuda().eval();original.load_state_dict(saved['model'])
    o=saved['env_obs'][:64].cuda();m=saved['env_mask'][:64].cuda()
    with torch.no_grad():
        a,v=model(o,m);b,w=original(o,m)
        assert torch.equal(a.probs,b.probs) and torch.equal(v,w)
        dist,_=model(o,m,temperature=torch.ones(64,device='cuda'));assert torch.equal(dist.probs,a.probs)
        temp=torch.where(torch.arange(64,device='cuda')<32,5.,1.)
        dist,_=model(o,m,temperature=temp);action=dist.sample();lp=dist.log_prob(action)
        torch.testing.assert_close(lp,dist.probs.gather(1,action[:,None]).squeeze(1).log(),atol=2e-6,rtol=1e-5)
        permutation=torch.randperm(64,device='cuda');updated,_=model(o[permutation],m[permutation],temperature=temp[permutation])
        torch.testing.assert_close((updated.log_prob(action[permutation])-lp[permutation]).exp(),torch.ones(64,device='cuda'),atol=1e-5,rtol=0)
    # Temperature-aware PPO must differentiate through both action heads/encoder.
    dist,_=model(o,m,temperature=temp);loss=-dist.log_prob(action).mean();loss.backward()
    assert model.body[0].weight.grad.isfinite().all() and model.direction[0].weight.grad.abs().sum()>0
    model.zero_grad(set_to_none=True)
    base=Env(64,24,corpus=pathlib.Path(manifest['corpus'])/'train',map_limit=8,library_path=job['train_library'])
    practice=TacticalEnv(64,24,corpus=ASSETS/'train',map_limit=64,library_path=job['tactical_library'])
    mixed=MixedEnv(base,practice,practice_worlds=8)
    ordinary_initial=base.state.clone();tactical_initial=practice.state.clone()
    with torch.no_grad():
        actions=model(mixed.obs,mixed.mask)[0].greedy();mixed.step(actions)
    assert torch.equal(base.state[:8],ordinary_initial[:8]) and torch.equal(practice.state[8:],tactical_initial[8:])
    assert mixed.counts[:2].tolist()==[56.,8.]
    snap=mixed.snapshot();raw=base.state.clone()
    with torch.no_grad():
        actions=model(mixed.obs,mixed.mask)[0].greedy();mixed.step(actions)
    expected=base.state.clone(),practice.state.clone(),mixed.obs.clone(),mixed.out.clone(),mixed.counts.clone()
    base.state.copy_(raw);mixed.restore(snap);mixed.step(actions)
    for actual,wanted in zip([base.state,practice.state,mixed.obs,mixed.out,mixed.counts],expected):assert torch.equal(actual,wanted)
    initial=Policy('d4_exact',128).cuda();initial.load_state_dict(torch.load(job['initial_model'],map_location='cpu',weights_only=False)['model'])
    from imitation_anchor import ImitationAnchor
    anchor=ImitationAnchor(initial,job)
    assert abs(float(anchor.loss(initial,o,m)))<1e-6
    assert all(not p.requires_grad for p in anchor.reference.parameters())
    with torch.no_grad():
        practice.reset(830001)
        pressure={}
        _,state=practice.probe();hard=state[:,6]>1
        for t in [1.,3.,5.]:
            d,_=model(practice.obs,practice.mask,temperature=torch.full((64,),t,device='cuda'))
            pressure[str(t)]=dict(move_probability=float(d.probs[:,:8].sum(1).mean()),pressure_move_probability=float(d.probs[hard,:8].sum(1).mean()),entropy=float(d.entropy().mean()))
    result=dict(checks='default model parity; unit-temperature parity; joint log probabilities; unchanged PPO ratio; finite gradients; inactive worlds; exact mixed-state replay; fixed original navigation anchor',practice_action_distributions=pressure,baseline=evaluate_tactics(model,job),controls=evaluate_tactics(model,job,controls=True),source_checkpoint_sha256=digest(SOURCE/'runs/navigation1-seed0/latest.pt'))
    for name in FAMILIES:
        teacher=result['controls']['teacher']['families'][name];cover=result['controls']['cover']['families'][name]
        print(name,'teacher',teacher['clear'],'cover',cover['clear'],flush=True)
    result['wall_seconds']=time.monotonic()-start
    (ROOT/'results/autoregressive-survival-preflight.json').write_text(json.dumps(result,indent=2)+'\n')
    print('All preflight checks passed',pressure,flush=True)

if __name__=='__main__':main()
