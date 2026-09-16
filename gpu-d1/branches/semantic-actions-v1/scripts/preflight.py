import ctypes as C,importlib.util,json,pathlib,subprocess,sys
import torch
from assets import ROOT,ASSETS,build
from run_experiment import plan
from learn_env_ring_multi import Env
from tactical_models import Policy
from symmetry import D4
import run_ring_ablations as runner

def native():
 torch.set_num_threads(1)
 spec=importlib.util.spec_from_file_location('map_compile',ROOT/'branches/vision15-choice-practice-v1/scripts/map_compile.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 maps=ASSETS/'test-map';maps.mkdir(exist_ok=True);module.compile_map(dict(floor=[(x,y) for x in range(-2,10) for y in range(-2,3)]),maps/'map-0.bin',0)
 env=Env(8,24,seed=17,corpus=maps,map_limit=1,library_path=ASSETS/'semantic-clump0-test.so')
 p=C.c_void_p;env.lib.semantic_self_test.argtypes=[p,p,p,p];result=torch.zeros(1,dtype=torch.int32,device='cuda')
 env.check(env.lib.semantic_self_test(C.byref(env.config),C.byref(env.tables),result.data_ptr(),env.stream));torch.cuda.synchronize();assert int(result[0])>1
 state=env.state.clone();obs=env.obs.clone();env.step(torch.full((8,),3,device='cuda',dtype=torch.long),active=torch.zeros(8,device='cuda',dtype=torch.bool));assert torch.equal(state,env.state) and torch.equal(obs,env.obs)
 model=Policy('d4_exact').cuda();o=env.obs.clone();mask=torch.ones(8,5,device='cuda');dist,v=model(o,mask);d=D4()
 for group in range(8):
  g=torch.full((8,),group,device='cuda',dtype=torch.long);q,w=model(d.observation(o,g),mask);torch.testing.assert_close(dist.probs,q.probs,atol=2e-6,rtol=2e-5);torch.testing.assert_close(v,w,atol=2e-6,rtol=2e-5)
 print('Native semantic action, interruption, physical-deadline, discounted-reward, inactive-state and D4 invariance checks passed.',flush=True)

def main():
 if '--native' in sys.argv:native();return
 build(0,True);subprocess.run([sys.executable,__file__,'--native'],check=True)
 m=plan();smoke=ROOT/'learning-runs/semantic-actions-smoke';smoke.mkdir(parents=True,exist_ok=True);store=runner.Store(smoke,2*runner.GIB,10*runner.GIB)
 m['jobs']=[dict(j,steps=512,batch=8,horizon=16,maps=2,validation_maps=2,eval_per_map=2,epochs=1,minibatch=128,checkpoint_every=256) for j in m['jobs']];store.json('manifest.json',m)
 for _ in range(2):subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',m['jobs'][0]['id'],'--output',str(smoke),'--max-disk-gb','2','--min-free-gb','10'],check=True)
 print('PPO smoke and completed-checkpoint resume passed.',flush=True)
if __name__=='__main__':main()
