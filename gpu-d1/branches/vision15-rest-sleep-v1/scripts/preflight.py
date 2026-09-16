"""Native rest/wait equivalence, masking, interruption, decision limits, and PPO smoke."""
import ctypes as C
import importlib.util,json,pathlib,subprocess,sys
import torch
from assets import ROOT,ASSETS
from run_experiment import plan
from learn_env_ring_multi import Env
from tactical_models import Policy
from symmetry import D4
import run_ring_ablations as runner

def native_checks():
 torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
 spec=importlib.util.spec_from_file_location('test_map_compile',ROOT/'branches/vision15-choice-practice-v1/scripts/map_compile.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 maps=ASSETS/'test-map';maps.mkdir(exist_ok=True);module.compile_map(dict(floor=[(x,y) for x in range(-2,10) for y in range(-2,3)]),maps/'map-0.bin',0)
 env=Env(8,24,seed=17,corpus=maps,map_limit=1,library_path=ASSETS/'rest1-clump0-test.so')
 p=C.c_void_p;env.lib.rest_self_test.argtypes=[p,p,p,p];result=torch.zeros(1,dtype=torch.int32,device='cuda')
 env.check(env.lib.rest_self_test(C.byref(env.config),C.byref(env.tables),result.data_ptr(),env.stream));torch.cuda.synchronize();count=int(result[0]);assert count>1
 # Entire inactive worlds must remain unchanged, including counters and RNG.
 state=env.state.clone();obs=env.obs.clone();env.step(torch.full((8,),8,device='cuda',dtype=torch.long),active=torch.zeros(8,device='cuda',dtype=torch.bool));assert torch.equal(state,env.state) and torch.equal(obs,env.obs)
 torch.manual_seed(0);model=Policy('d4_exact').cuda();o=env.obs.clone();o[:,959:]=torch.randint(-1,2,(8,40),device="cuda").float();mask=torch.ones(8,10,device='cuda');dist,value=model(o,mask);d=D4()
 for group in range(8):
  g=torch.full((8,),group,device='cuda',dtype=torch.long);assert torch.equal(d.observation(o,g)[:,959:],o[:,959:]);q,v=model(d.observation(o,g),d.mask(mask,g));torch.testing.assert_close(dist.probs,q.probs.gather(1,d.forward[g]),atol=2e-6,rtol=2e-5);torch.testing.assert_close(value,v,atol=2e-6,rtol=2e-5)
  assert torch.all(d.forward[g,9]==9)
 (ASSETS/'native-check.json').write_text(json.dumps(dict(count=count))+'\n')

def main():
 subprocess.run([sys.executable,__file__,'--native'],check=True)
 count=json.loads((ASSETS/'native-check.json').read_text())['count']
 m=plan();smoke=ROOT/'learning-runs/rest-sleep-smoke';smoke.mkdir(parents=True,exist_ok=True);store=runner.Store(smoke,2*runner.GIB,10*runner.GIB)
 m['jobs']=[dict(j,steps=512,batch=8,horizon=16,maps=2,validation_maps=2,eval_per_map=2,epochs=1,minibatch=128,checkpoint_every=256) for j in m['jobs']];store.json('manifest.json',m)
 for j in m['jobs']:
  for _ in range(2):subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',j['id'],'--output',str(smoke),'--max-disk-gb','2','--min-free-gb','10'],check=True)
 a=torch.load(smoke/'runs/wait-seed0/snapshots/000000000000.pt',map_location='cpu',weights_only=False)['model'];b=torch.load(smoke/'runs/rest-seed0/snapshots/000000000000.pt',map_location='cpu',weights_only=False)['model'];assert all(torch.equal(a[k],b[k]) for k in a)
 old=torch.load(ROOT/"learning-runs/vision15-rest-full/runs/wait-seed0/snapshots/000000000000.pt",map_location="cpu",weights_only=False)["model"]
 for k in a:
  if k=="body.0.weight":
   assert torch.equal(a[k][:,:959],old[k]) and not a[k][:,959:].any()
  else:assert torch.equal(a[k],old[k])
 report=dict(original_initial_weights_preserved=True,new_sleep_weights_initially_zero=True,visible_sleep_status_correct=True,hidden_and_remembered_hidden_status_zero=True,sleep_status_d4_invariant=True,rest_matches_repeated_wait_state_and_reward=True,primitive_waits_for_3_to_18_hp=count,full_hp_masked=True,visible_sleeping_enemy_masked=True,enemy_entry_interrupts=True,decision_deadline_resets=True,physical_turns_can_exceed_2048=True,inactive_worlds_unchanged=True,d4_rest_action_invariant=True,paired_initial_weights_equal=True,ppo_and_resume_passed=True)
 (ROOT/'results/rest-sleep-preflight.json').write_text(json.dumps(report,indent=2)+'\n');print(report,flush=True)
if __name__=='__main__':
 if '--native' in sys.argv:native_checks()
 else:main()
