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
 env=Env(8,24,seed=17,corpus=maps,map_limit=1,library_path=ASSETS/'autoregressive-clump0-test.so')
 p=C.c_void_p;env.lib.autoregressive_self_test.argtypes=[p,p,p,p];result=torch.zeros(1,dtype=torch.int32,device='cuda')
 env.check(env.lib.autoregressive_self_test(C.byref(env.config),C.byref(env.tables),result.data_ptr(),env.stream));torch.cuda.synchronize();assert int(result[0])>1
 state=env.state.clone();obs=env.obs.clone();env.step(torch.full((8,),16,device='cuda',dtype=torch.long),active=torch.zeros(8,device='cuda',dtype=torch.bool));assert torch.equal(state,env.state) and torch.equal(obs,env.obs)
 model=Policy('d4_exact').cuda();o=env.obs.clone();mask=env.mask.clone();dist,v=model(o,mask);d=D4()
 for group in range(8):
  g=torch.full((8,),group,device='cuda',dtype=torch.long)
  forward=torch.cat((d.forward[group,:8],8+d.forward[group,:8],torch.tensor([16,17],device='cuda')))
  transformed_mask=mask[:,forward.argsort()]
  q,w=model(d.observation(o,g),transformed_mask)
  torch.testing.assert_close(dist.probs,q.probs[:,forward],atol=2e-6,rtol=2e-5);torch.testing.assert_close(v,w,atol=2e-6,rtol=2e-5)
 from tactical_models import ActionDistribution
 from torch.distributions import Categorical
 masks=torch.zeros(4,18,device='cuda');masks[:,16]=1;masks[0,0]=1;masks[1,9]=1;masks[2,:]=1
 types=torch.randn(4,4,device='cuda',requires_grad=True);directions=torch.randn(4,2,8,device='cuda',requires_grad=True)
 dist=ActionDistribution(types,directions,masks);joint=Categorical(probs=dist.probs)
 torch.testing.assert_close(dist.entropy(),joint.entropy())
 for _ in range(20):
  a=dist.sample();assert bool(masks.gather(1,a[:,None]).all());torch.testing.assert_close(dist.log_prob(a),joint.log_prob(a),atol=2e-6,rtol=2e-5)
 assert dist.probs[3,16]==1 and dist.greedy()[3]==16
 (-dist.log_prob(dist.sample()).mean()-.01*dist.entropy().mean()).backward()
 assert torch.isfinite(types.grad).all() and torch.isfinite(directions.grad).all()
 print('Native autoregressive action, interruption, physical-deadline, discounted-reward, inactive-state and D4 invariance checks passed.',flush=True)


def reward_check():
 torch.set_num_threads(1)
 worlds=[Env(16,24,seed=371,corpus=ROOT/'fixtures/d1-corpus-388/validation',map_limit=2,library_path=p) for p in [ROOT/'learning-runs/autoregressive-imitation-assets/autoregressive-clump0.so',ASSETS/'autoregressive-clump0.so']]
 torch.manual_seed(23);rest_turns=0
 for _ in range(80):
  base,new=worlds;a=torch.multinomial(base.mask,1).squeeze(1);a=torch.where(base.mask[:,17]>0,17,a)
  for env in worlds:env.step(a)
  for field in ['state','obs','mask']:assert torch.equal(getattr(base,field),getattr(new,field))
  cols=[i for i in range(42) if i not in [0,40]];assert torch.equal(base.out[:,cols],new.out[:,cols])
  torch.testing.assert_close(new.out[:,0],base.out[:,0]-.00001*new.out[:,26],rtol=0,atol=2e-6)
  torch.testing.assert_close(new.out[:,40],new.out[:,0],rtol=0,atol=2e-6)
  rest_turns+=int(new.out[:,35].sum())
 assert rest_turns>0
 print('Only reward changes; physical-turn penalty verified including',rest_turns,'REST turns.',flush=True)

def main():
 if '--native' in sys.argv:native();return
 build(0,True);subprocess.run([sys.executable,__file__,'--native'],check=True);reward_check()
 m=plan();smoke=ROOT/'learning-runs/autoregressive-turn-cost-smoke';smoke.mkdir(parents=True,exist_ok=True);store=runner.Store(smoke,2*runner.GIB,10*runner.GIB)
 m['jobs']=[dict(j,steps=500,batch=8,horizon=16,maps=2,validation_maps=2,eval_per_map=2,epochs=1,minibatch=128,checkpoint_every=256) for j in m['jobs']];store.json('manifest.json',m)
 for _ in range(2):subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',m['jobs'][0]['id'],'--output',str(smoke),'--max-disk-gb','2','--min-free-gb','10'],check=True)
 result=json.loads((smoke/'runs'/m['jobs'][0]['id']/'result.json').read_text());assert result['decisions']==504
 print('PPO partial-rollout smoke and completed-checkpoint resume passed.',flush=True)
if __name__=='__main__':main()
