"""Compare raw shaped reward and physical-turn-discounted episodic return."""
import sys,pathlib,json,time,hashlib
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'branches/semantic-actions-v1/scripts'))
from tactical_models import Policy
from learn_env_ring_multi import Env

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
@torch.no_grad()
def main():
 torch.set_num_threads(1);torch.distributions.Distribution.set_default_validate_args(False)
 suite=ROOT/'learning-runs/semantic-actions';manifest=json.loads((suite/'manifest.json').read_text());job=manifest['jobs'][0]
 cp=suite/'runs/semantic-seed0/latest.pt';saved=torch.load(cp,map_location='cpu',weights_only=False)
 model=Policy(job['architecture'],job['width']).cuda();model.load_state_dict(saved['model']);model.eval()
 lib=pathlib.Path(job['eval_library']);assert digest(lib)==lib.with_suffix('.sha256').read_text().strip()
 env=Env(1024,24,seed=900000,corpus=pathlib.Path(manifest['corpus'])/'validation',map_limit=32,map_filter=-2,library_path=lib,limit=2048)
 results={}
 for key in ['deterministic']+[m+'_'+v for m in ['sampled','greedy'] for v in ['baseline','rest','rest_wait','rest_attack_wait']]:
  env.reset(900000);torch.manual_seed(900000);active=torch.ones(1024,device='cuda',dtype=torch.bool)
  raw=torch.zeros(1024,device='cuda',dtype=torch.float64);discounted=raw.clone();factor=torch.ones_like(raw);turns=raw.clone();terminal=torch.zeros_like(env.out);start=time.monotonic()
  for _ in range(2048):
   if not active.any():break
   if key=='deterministic':a=env.heuristic().clone()
   else:
    dist,_=model(env.obs,env.mask);a=dist.sample() if key.startswith('sampled') else dist.probs.argmax(-1)
    if 'rest' in key:a=torch.where(env.mask[:,4]>0,4,a)
    if 'wait' in key:
     h=env.heuristic().clone();a=torch.where(h==3,h,a)
     if 'attack' in key:a=torch.where(h==0,h,a)
   assert bool(((env.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all())
   env.step(a,active=active)
   raw+=active*env.out[:,0];discounted+=active*factor*env.out[:,40];turns+=active*env.out[:,26]
   factor*=torch.where(active,.99**env.out[:,26].double(),1.)
   ended=active&(env.out[:,1]>0);terminal[ended]=env.out[ended];active&=~ended
  assert not active.any();assert torch.equal(turns,terminal[:,5].double())
  torch.testing.assert_close(factor,.99**turns,rtol=1e-10,atol=1e-12)
  t=terminal.cpu();metrics=dict(raw_reward=float(raw.mean()),discounted_return=float(discounted.mean()),clears=int(t[:,2].sum()),deaths=int(t[:,6].sum()),timeouts=int(t[:,7].sum()),turns=float(turns.mean()),seconds=time.monotonic()-start)
  results[key]=dict(metrics=metrics,episodes=[dict(map_seed=env.metadata[i%32]['seed'],raw_reward=float(raw[i]),discounted_return=float(discounted[i]),clear=bool(t[i,2]),death=bool(t[i,6]),timeout=bool(t[i,7]),turns=int(t[i,5])) for i in range(1024)])
  print(key,json.dumps(metrics),flush=True)
 report=dict(gamma=.99,discount_unit='physical_turn',formula='sum over macro decisions of gamma^(prior elapsed turns) * sum over internal turns of gamma^internal_index * reward',checkpoint_sha256=digest(cp),library_sha256=digest(lib),script_sha256=digest(pathlib.Path(__file__)),results=results)
 (ROOT/'results/semantic-actions-reward-scores.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
