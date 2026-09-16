import pathlib,sys,subprocess,json,ctypes
import torch
from assets import ROOT,ASSETS
from run_experiment import plan
import run_ring_ablations as runner
from learn_env_ring_multi import Env

def main():
 torch.set_num_threads(1);worlds=[]
 for lib in [ROOT/'learning-runs/semantic-actions-assets/semantic-clump0.so',ASSETS/'gamma0.99-clump0.so',ASSETS/'gamma1.0-clump0.so']:
  worlds.append(Env(16,24,seed=371,corpus=ROOT/'fixtures/d1-corpus-388/validation',map_limit=2,library_path=lib,limit=2048))
 torch.manual_seed(23);rest_turns=0
 for _ in range(80):
  base=worlds[0]
  a=torch.multinomial(base.mask,1).squeeze(1)
  # Exercise recovery as soon as it is legal, plus all other available actions.
  a=torch.where((base.mask[:,4]>0),4,a)
  for env in worlds:env.step(a)
  for env in worlds[1:]:
   assert torch.equal(base.state,env.state) and torch.equal(base.obs,env.obs) and torch.equal(base.mask,env.mask)
  assert torch.equal(base.out,worlds[1].out)
  indices=[i for i in range(42) if i!=40];assert torch.equal(base.out[:,indices],worlds[2].out[:,indices])
  assert torch.equal(worlds[2].out[:,40],worlds[2].out[:,0])
  rest_turns+=int(worlds[2].out[:,35].sum())
 assert rest_turns>0
 print('Physics, observations and masks identical across old/new .99 and gamma=1; gamma=1 macro rewards equal raw sums. Rest turns tested:',rest_turns,flush=True)
 m=plan();m['jobs']=[dict(m['jobs'][1],steps=500,batch=8,horizon=16,maps=2,validation_maps=1,eval_per_map=1,epochs=1,minibatch=128,checkpoint_every=250)]
 smoke=ROOT/'learning-runs/semantic-discount-smoke';smoke.mkdir(exist_ok=True);store=runner.Store(smoke,2*runner.GIB,10*runner.GIB);store.json('manifest.json',m)
 for _ in range(2):subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',m['jobs'][0]['id'],'--output',str(smoke),'--max-disk-gb','2','--min-free-gb','10'],check=True)
 result=json.loads((smoke/'runs'/m['jobs'][0]['id']/'result.json').read_text());assert result['decisions']==504
 print('Short final rollout and resume passed at 504 decisions for a 500-decision target.',flush=True)
if __name__=='__main__':main()
