"""Training-only reference buffer and fixed-reference PPO protection screen."""
import argparse, fcntl, json, pathlib, subprocess, sys, time
import torch
import episode_credit as ec
import run_ring_ablations as runner
from tactical_models import Policy
from learn_env_ring_multi import Env
from imitation_anchor import ImitationAnchor
ROOT=ec.ROOT


def prepare(base, corpus, path):
    torch.set_num_threads(1)
    with torch.random.fork_rng(devices=[0]):
        torch.manual_seed(82371)
        model=Policy(base['architecture'],base['width']).cuda()
        model.load_state_dict(torch.load(base['initial_model'],weights_only=False)['model'])
        if not path.exists():
            env=Env(128,24,seed=82371,corpus=pathlib.Path(corpus)/'train',map_limit=256,library_path=base['train_library'],limit=2048)
            obs=[]; masks=[]
            with torch.no_grad():
                for _ in range(512):
                    obs.append(env.obs.cpu().clone()); masks.append(env.mask.cpu().clone())
                    env.step(model(env.obs,env.mask)[0].sample())
            torch.save(dict(obs=torch.cat(obs),mask=torch.cat(masks),corpus=str(pathlib.Path(corpus)/'train'),seed=82371,source_sha256=base['initial_model_sha256']),path)
            del env,obs,masks
        # Verify zero loss at initialization, restoring force after perturbation,
        # no reference gradients, and no gradients outside first layer for features.
        for kind in ['feature','policy']:
            anchor=ImitationAnchor(model,dict(anchor_kind=kind,anchor_weight=1,anchor_buffer=str(path)))
            x,m=anchor.obs[:64],anchor.mask[:64]
            assert abs(anchor.loss(model,x,m).item())<1e-6
            original=model.body[0].bias.detach().clone()
            with torch.no_grad():model.body[0].bias.add_(.01)
            model.zero_grad();loss=anchor.loss(model,x,m);assert loss.item()>0;loss.backward()
            assert all(p.grad is None for p in anchor.reference.parameters())
            assert model.body[0].bias.grad.abs().sum()>0
            if kind=='feature':assert model.body[2].weight.grad is None
            with torch.no_grad():model.body[0].bias.copy_(original)
            del anchor
        print('Anchor zero-loss, perturbation, gradient isolation, and fixed-reference checks passed',flush=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--variants',default='feature10,feature100,policy001,policy01');ap.add_argument('--seed',type=int,default=0);ap.add_argument('--steps',type=int,default=10000000);ap.add_argument('--name',default='autoregressive-anchor-screen');args=ap.parse_args()
    suite=ROOT/'learning-runs'/args.name;suite.mkdir(parents=True,exist_ok=True)
    store=runner.Store(suite,3*runner.GIB,10*runner.GIB)
    with (suite/'.pipeline.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old=json.loads((ROOT/'learning-runs/autoregressive-turn-cost/manifest.json').read_text());base=old['jobs'][0]
        buffer=ROOT/'learning-runs/autoregressive-anchor-buffer.pt';prepare(base,old['corpus'],buffer)
        variants=dict(feature10=('feature',10.),feature100=('feature',100.),policy001=('policy',.01),policy01=('policy',.1))
        jobs=[dict(base,id=f'{name}-seed{args.seed}',name=name,seed=args.seed,steps=args.steps,evaluation_steps=[1000000,5000000,10000000],anchor_kind=variants[name][0],anchor_weight=variants[name][1],anchor_batch=512,anchor_buffer=str(buffer),anchor_buffer_sha256=runner.digest(buffer)) for name in args.variants.split(',')]
        manifest=dict(corpus=old['corpus'],jobs=jobs,sources={str(p):runner.digest(p) for p in [pathlib.Path(__file__),pathlib.Path(runner.__file__),pathlib.Path(runner.__file__).with_name('imitation_anchor.py')]})
        if (suite/'manifest.json').exists():assert json.loads((suite/'manifest.json').read_text())==manifest
        else:store.json('manifest.json',manifest)
        start=time.monotonic();result={}
        for job in jobs:
            store.json('status.json',dict(status='training',job=job['id']));folder=suite/'runs'/job['id']
            if not (folder/'result.json').exists():subprocess.run([sys.executable,str(pathlib.Path(runner.__file__)),'--worker',job['id'],'--output',str(suite),'--max-disk-gb','3','--min-free-gb','10'],check=True)
            result[job['id']]=dict(ppo=json.loads((folder/'result.json').read_text()),evaluations=json.loads((folder/'curve.json').read_text()))
            (ROOT/'results'/f'{args.name}.json').write_text(json.dumps(dict(results=result,wall_seconds=time.monotonic()-start),indent=2)+'\n')
        store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start))
if __name__=='__main__':main()
