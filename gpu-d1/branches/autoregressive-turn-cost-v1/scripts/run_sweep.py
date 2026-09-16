"""Matched seed-0 physical-turn cost sweep; retain only bounded checkpoints."""
import ctypes,fcntl,json,pathlib,subprocess,sys,time
import torch
from assets import ROOT,build
from learn_env_ring_multi import Env
import run_ring_ablations as runner

SUITE=ROOT/'learning-runs/autoregressive-turn-sweep'
VALUES=[3,10,30,100]

def verify(n,library):
 torch.set_num_threads(1)
 paths=[ROOT/'learning-runs/autoregressive-imitation-assets/autoregressive-clump0.so',library]
 worlds=[Env(16,24,seed=371,corpus=ROOT/'fixtures/d1-corpus-388/validation',map_limit=2,library_path=p) for p in paths]
 worlds[1].lib.learn_turn_cost.restype=ctypes.c_float
 assert abs(worlds[1].lib.learn_turn_cost()-n*.00001)<1e-9
 torch.manual_seed(23);rest_turns=0
 for _ in range(80):
  base,new=worlds;a=torch.multinomial(base.mask,1).squeeze(1);a=torch.where(base.mask[:,17]>0,17,a)
  for env in worlds:env.step(a)
  for field in ['state','obs','mask']:assert torch.equal(getattr(base,field),getattr(new,field))
  cols=[i for i in range(42) if i not in [0,40]];assert torch.equal(base.out[:,cols],new.out[:,cols])
  torch.testing.assert_close(new.out[:,0],base.out[:,0]-n*.00001*new.out[:,26],rtol=0,atol=2e-6)
  torch.testing.assert_close(new.out[:,40],new.out[:,0],rtol=0,atol=2e-6)
  rest_turns+=int(new.out[:,35].sum())
 assert rest_turns>0
 print('Reward/physics preflight passed',n,'REST turns',rest_turns,flush=True)
 return dict(rest_turns=rest_turns,unchanged_physics=True)

def main():
 SUITE.mkdir(parents=True,exist_ok=True);start=time.monotonic();store=runner.Store(SUITE,2*runner.GIB,10*runner.GIB)
 with (SUITE/'.pipeline.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  old=json.loads((ROOT/'learning-runs/autoregressive-turn-cost/manifest.json').read_text())
  source=old['jobs'][0];assert runner.digest(pathlib.Path(source['initial_model']))==source['initial_model_sha256']
  jobs=[dict(source,id=f'turn-cost-n{n}-seed0',name=f'turn-cost-n{n}',turn_cost_n=n,turn_reward=-n*.00001,turn_milli=-n*.01,evaluation_steps=[500000,1000000],train_library=str(ROOT/f'learning-runs/autoregressive-turn-sweep-assets/autoregressive-clump1-n{n}.so'),eval_library=str(ROOT/f'learning-runs/autoregressive-turn-sweep-assets/autoregressive-clump0-n{n}.so')) for n in VALUES]
  manifest=dict(format='autoregressive-turn-sweep-v1',corpus=old['corpus'],jobs=jobs,reused={0:'results/autoregressive-imitation-no-entropy.json',1:'results/autoregressive-turn-cost.json'},sources={str(p.relative_to(runner.ROOT)):runner.digest(p) for sub in ['scripts','src'] for p in sorted((runner.ROOT/sub).iterdir()) if p.suffix in ['.py','.cu','.h']})
  if (SUITE/'manifest.json').exists():assert json.loads((SUITE/'manifest.json').read_text())==manifest
  else:store.json('manifest.json',manifest)
  results={str(n):json.loads((ROOT/p).read_text()) for n,p in manifest['reused'].items()}
  for j in jobs:
   n=j['turn_cost_n'];store.json('status.json',dict(status='running',n=n,started_at=time.time()))
   dest=SUITE/'runs'/j['id']/'result.json'
   if not dest.exists():
    for clump in [0,1]:build(clump,n=n)
    check=verify(n,pathlib.Path(j['eval_library']));store.json(f'preflight-n{n}.json',check)
    subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',j['id'],'--output',str(SUITE),'--max-disk-gb','2','--min-free-gb','10'],check=True)
   result=json.loads(dest.read_text());curve=json.loads(dest.with_name('curve.json').read_text());assert [r['decisions'] for r in curve]==[0,500224,1000448]
   # All conditions begin with exactly the same behavior, independent of reward.
   for mode in ['sampled','greedy']:
    ref=results['1']['evaluations'][0][mode]
    for key in ['clear_rate','death_rate','timeout_rate','turns','rest_uses','actions']:assert curve[0][mode][key]==ref[key]
   results[str(n)]=dict(ppo=result,evaluations=curve)
   (ROOT/'results/autoregressive-turn-sweep.json').write_text(json.dumps(dict(results=results,wall_seconds=time.monotonic()-start),indent=2)+'\n')
  store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Sweep complete',flush=True)
if __name__=='__main__':main()
