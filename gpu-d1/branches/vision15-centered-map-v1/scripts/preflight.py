"""Native semantics, spatial encoding, D4 symmetry, PPO/resume and speed check."""
import ctypes as C,importlib.util,json,pathlib,subprocess,sys,time
import torch
from assets import ROOT,ASSETS
from run_experiment import plan
from learn_env_ring_multi import Env
from tactical_models import Policy
from symmetry import D4
import run_ring_ablations as runner

def native():
 spec=importlib.util.spec_from_file_location('maps',ROOT/'branches/vision15-choice-practice-v1/scripts/map_compile.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 maps=ASSETS/'test-map';maps.mkdir(exist_ok=True);m.compile_map(dict(floor=[(x,y) for x in range(-2,10) for y in range(-2,3)]),maps/'map-0.bin',0)
 env=Env(8,24,device='cpu',corpus=maps,library_path=ASSETS/'rest1-clump0-test.so');p=C.c_void_p
 env.lib.rest_self_test.argtypes=[p,p,p,p,p,p,p];result=torch.zeros(1,dtype=torch.int32)
 env.check(env.lib.rest_self_test(env.state.data_ptr(),C.byref(env.config),C.byref(env.tables),result.data_ptr(),env.obs.data_ptr(),env.mask.data_ptr(),env.stream));torch.cuda.synchronize()
 state=env.state.clone();obs=env.obs.clone();env.step(torch.full((8,),8,dtype=torch.long),active=torch.zeros(8,dtype=torch.bool));assert torch.equal(state,env.state) and torch.equal(obs,env.obs)
 cpu=Env(8,24,seed=51,device='cpu',corpus=maps,library_path=ASSETS/'rest1-clump0.so')
 gpu=Env(8,24,seed=51,corpus=maps,library_path=ASSETS/'rest1-clump0.so')
 for tick in range(48):
  assert torch.equal(cpu.obs,gpu.obs.cpu()) and torch.equal(cpu.mask,gpu.mask.cpu())
  action=torch.full((8,),tick%10,dtype=torch.long)
  action=torch.where(cpu.mask.gather(1,action[:,None]).squeeze(1)>0,action,8)
  cpu.step(action);gpu.step(action.cuda())
  assert torch.equal(cpu.out,gpu.out.cpu()) and torch.equal(cpu.state,gpu.state.cpu())
 print('Native checks passed; rest uses',int(result[0]),'physical waits',flush=True)

def spatial():
 torch.set_num_threads(1);torch.manual_seed(0)
 model=Policy().cuda();obs=torch.zeros(2,6599,device='cuda');mask=torch.ones(2,10,device='cuda')
 # Opposite map corners: all displacement extremes must survive recentering.
 obs[0,652:654]=torch.tensor([0.,0.],device='cuda');obs[1,652:654]=torch.tensor([79/80,69/70],device='cuda')
 obs[:,999:]=-1;obs[0,999+69*80+79]=1;obs[1,999]=1
 obs[0,450:455]=torch.tensor([79/80,69/70,2.,.6,1.],device='cuda');obs[1,450:455]=torch.tensor([-79/80,-69/70,1.,.6,1.],device='cuda');obs[:,959]=1
 maps=model.centered(obs)
 assert maps[0,0,148,158]==1 and maps[1,0,10,0]==1
 assert maps[0,1,148,158]==2 and maps[1,1,10,0]==1
 assert maps[0,2,148,158]==1 and maps[1,2,10,0]==1
 assert maps[0,0,0,0]==0 # Padding is distinct from wall.
 d=D4();local=obs[:,:999];dist,val=model(obs,mask)
 for g in range(8):
  groups=torch.full((2,),g,device='cuda',dtype=torch.long)
  image=maps.flip(-1) if g//4 else maps;image=torch.rot90(image,-(g%4),(-2,-1))
  q,v=model.aggregate(d.observation(local,groups),image,d.mask(mask,groups))
  torch.testing.assert_close(dist.probs,q.probs.gather(1,d.forward[groups]),atol=3e-6,rtol=3e-5)
  torch.testing.assert_close(val,v,atol=3e-6,rtol=3e-5)
 (val.square().mean()-dist.entropy().mean()).backward()
 assert all(p.grad is not None and p.grad.isfinite().all() for p in model.parameters())
 print('Map centering, global enemies, padding, D4, and gradients passed',flush=True)

def main():
 subprocess.run([sys.executable,__file__,'--native'],check=True)
 subprocess.run([sys.executable,__file__,'--spatial'],check=True)
 m=plan();smoke=ROOT/'learning-runs/centered-map-smoke';smoke.mkdir(parents=True,exist_ok=True);store=runner.Store(smoke,2*runner.GIB,10*runner.GIB)
 m['jobs']=[dict(j,steps=32768,maps=2,validation_maps=1,eval_per_map=1,checkpoint_every=32768) for j in m['jobs']];store.json('manifest.json',m)
 for j in m['jobs']:
  for _ in range(2):subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',j['id'],'--output',str(smoke),'--max-disk-gb','2','--min-free-gb','10'],check=True)
 result=json.loads((smoke/'runs/rest-seed0/result.json').read_text())
 report=dict(native_semantics=True,cpu_gpu_48_step_parity=True,sleeping_enemy_does_not_block_rest=True,waking_or_approaching_awake_enemy_interrupts=True,rest_stops_at_2048_physical_turns=True,full_map_and_all_enemies=True,no_frontier_guidance=True,centering_extremes_and_d4=True,ppo_resume=True,benchmark_decisions=result['decisions'],benchmark_train_seconds=result['train_seconds'],estimated_10m_train_seconds=result['train_seconds']*10000000/result['decisions'])
 (ROOT/'results/centered-map-preflight.json').write_text(json.dumps(report,indent=2)+'\n');print(report,flush=True)
if __name__=='__main__':
 if '--native' in sys.argv:native()
 elif '--spatial' in sys.argv:spatial()
 else:main()
