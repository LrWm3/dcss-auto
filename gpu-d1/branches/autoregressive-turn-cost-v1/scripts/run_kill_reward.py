"""Add +.01 per kill to the original tiny-turn-cost streaming PPO experiment."""
import fcntl,json,pathlib,subprocess,sys,time
import torch
from assets import ROOT,FLAGS
from learn_env_ring_multi import Env
from tactical_models import Policy
import run_ring_ablations as runner
SUITE=ROOT/'learning-runs/autoregressive-kill001'
ASSETS=ROOT/'learning-runs/autoregressive-kill001-assets'

def build(clump):
 ASSETS.mkdir(parents=True,exist_ok=True);lib=ASSETS/f'autoregressive-clump{clump}.so'
 flags=[f for f in FLAGS if not f.startswith('-DKILL_MILLI=')]+['-DKILL_MILLI=10']
 subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*flags,f'-DCLUMP_MODE={clump}',str(runner.ROOT/'src/learn.cu'),'-o',str(lib)],check=True)
 lib.with_suffix('.sha256').write_text(runner.digest(lib)+'\n');return lib

def verify(job):
 torch.set_num_threads(1);torch.manual_seed(0)
 paths=[ROOT/'learning-runs/autoregressive-turn-cost-assets/autoregressive-clump0.so',ASSETS/'autoregressive-clump0.so']
 worlds=[Env(16,24,seed=371,corpus=ROOT/'fixtures/d1-corpus-388/validation',map_limit=2,library_path=p,limit=2048) for p in paths]
 model=Policy('d4_exact',128).cuda();model.load_state_dict(torch.load(job['initial_model'],map_location='cpu',weights_only=False)['model'])
 previous=torch.zeros(16,device='cuda');kills=rests=0
 with torch.no_grad():
  for _ in range(512):
   base,new=worlds;dist,_=model(base.obs,base.mask);a=dist.sample()
   for env in worlds:env.step(a)
   for field in ['state','obs','mask']:assert torch.equal(getattr(base,field),getattr(new,field))
   cols=[i for i in range(42) if i not in [0,40]];assert torch.equal(base.out[:,cols],new.out[:,cols])
   delta=base.out[:,3]-previous;assert (delta>=0).all()
   torch.testing.assert_close(new.out[:,0],base.out[:,0]+.01*delta,rtol=0,atol=2e-6)
   torch.testing.assert_close(new.out[:,40],new.out[:,0],rtol=0,atol=2e-6)
   previous=torch.where(base.out[:,1]>0,0,base.out[:,3]);kills+=int(delta.sum());rests+=int(new.out[:,35].sum())
 assert kills>0 and rests>0
 return dict(steps=512,worlds=16,kills=kills,physical_rest_turns=rests,unchanged_physics=True)

def main():
 SUITE.mkdir(parents=True,exist_ok=True);store=runner.Store(SUITE,2*runner.GIB,10*runner.GIB);start=time.monotonic()
 with (SUITE/'.pipeline.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  try:
   old=json.loads((ROOT/'learning-runs/autoregressive-turn-cost/manifest.json').read_text())
   job=dict(old['jobs'][0],id='kill001-seed0',name='kill001',kill_milli=10,reward_scheme='clear_plus_small_kill_minus_turn_cost',train_library=str(ASSETS/'autoregressive-clump1.so'),eval_library=str(ASSETS/'autoregressive-clump0.so'))
   assert runner.digest(pathlib.Path(job['initial_model']))==job['initial_model_sha256']
   m=dict(format='autoregressive-kill001-v1',corpus=old['corpus'],jobs=[job],control='results/autoregressive-turn-cost.json',sources={str(p.relative_to(runner.ROOT)):runner.digest(p) for sub in ['scripts','src'] for p in sorted((runner.ROOT/sub).iterdir()) if p.suffix in ['.py','.cu','.h']})
   if (SUITE/'manifest.json').exists():assert json.loads((SUITE/'manifest.json').read_text())==m
   else:store.json('manifest.json',m)
   store.json('status.json',dict(status='building',started_at=time.time()))
   for clump in [0,1]:build(clump)
   check=verify(job);store.json('preflight.json',check);print('Preflight',json.dumps(check),flush=True)
   store.json('status.json',dict(status='training',started_at=time.time()))
   subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',job['id'],'--output',str(SUITE),'--max-disk-gb','2','--min-free-gb','10'],check=True)
   folder=SUITE/'runs'/job['id'];result=json.loads((folder/'result.json').read_text());curve=json.loads((folder/'curve.json').read_text());assert [r['decisions'] for r in curve]==[0,500224,1000448]
   reference=json.loads((ROOT/'results/autoregressive-turn-cost.json').read_text())['evaluations'][0]
   for mode in ['sampled','greedy']:
    for key in ['clear_rate','death_rate','timeout_rate','turns','rest_uses','actions']:assert curve[0][mode][key]==reference[mode][key]
   output=dict(ppo=result,evaluations=curve,preflight=check,wall_seconds=time.monotonic()-start,change='Only add +.01 per required kill to original streaming tiny-turn-cost PPO; not the complete-episode collector. Same initialization and seed.')
   (ROOT/'results/autoregressive-kill001.json').write_text(json.dumps(output,indent=2)+'\n')
   store.json('status.json',dict(status='navigation_audit',wall_seconds=time.monotonic()-start))
   subprocess.run([sys.executable,str(ROOT/'diagnostics/autoregressive-imitation/navigation_audit.py'),'--suite','autoregressive-kill001','--result','autoregressive-kill001','--output','autoregressive-kill001-navigation','--stages','500224','1000448','--modes','type_greedy'],check=True)
   store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Kill reward experiment complete',flush=True)
  except Exception as exc:
   store.json('status.json',dict(status='failed',failure=f'{type(exc).__name__}: {exc}',wall_seconds=time.monotonic()-start));raise
if __name__=='__main__':main()
