"""Copy the finished 30M seed-0 run into a separate, instrumented 150M suite."""
import json,pathlib,shutil,torch
import run_ring_ablations as runner
root=runner.ROOT.parents[1]
source=root/'learning-runs/ogre2-baseline-30m'
target=root/'learning-runs/ogre2-baseline-150m'
if target.exists():
    raise RuntimeError(f'Refusing to overwrite {target}')
manifest=json.loads((source/'manifest.json').read_text())
assert len(manifest['jobs'])==1
job=manifest['jobs'][0]
assert job['name']=='ogre2_base' and job['seed']==0 and job['steps']==30_000_000
job['steps']=150_000_000
job['performance']='fast'
manifest['sources']={p:runner.digest(runner.ROOT/p) for p in runner.SOURCE_FILES}
saved_path=source/'runs'/job['id']/'latest.pt'
saved=torch.load(saved_path,map_location='cpu',weights_only=False)
assert saved['decisions']>=30_000_000
assert saved['job'] | {'steps':150_000_000, 'performance':'fast'} == job
saved['job']=dict(job)
if saved['best'] is not None:saved['best']['job']=dict(job)
folder=target/'runs'/job['id'];folder.mkdir(parents=True)
(target/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
torch.save(saved,folder/'latest.pt')
(target/'continuation.json').write_text(json.dumps(dict(source=str(saved_path),sha256=runner.digest(saved_path),start_decisions=saved['decisions'],prior_train_seconds=saved['train_seconds'],changes='Output-only ogre diagnostics; no State layout, dynamics, policy inputs, rewards or PPO changes'),indent=2)+'\n')
from ablation_storage import Store
runner.build(Store(target,2*runner.GIB,5*runner.GIB),job)
print(target)
