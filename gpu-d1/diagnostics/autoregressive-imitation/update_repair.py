"""Post-hoc encoder grafts on independently trained degraded checkpoints."""
import json,pathlib,time,torch
import episode_credit as ec
from tactical_models import Policy
ROOT=ec.ROOT

def main():
 torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
 from torch.distributions import Distribution
 Distribution.set_default_validate_args(False)
 manifest=json.loads((ROOT/'learning-runs/autoregressive-turn-cost/manifest.json').read_text());base=manifest['jobs'][0];corpus=pathlib.Path(manifest['corpus']);initial=torch.load(base['initial_model'],map_location='cpu',weights_only=False)['model']
 paths={'turn_cost':ROOT/'learning-runs/autoregressive-turn-cost/runs/turn-cost-seed0/snapshots/000001000448.pt','kill_reward':ROOT/'learning-runs/autoregressive-kill001/runs/kill001-seed0/snapshots/000001000448.pt','episode_return':ROOT/'learning-runs/autoregressive-episode-credit/episode_return/latest.pt'}
 results={};start=time.monotonic()
 for name,path in paths.items():
  saved=torch.load(path,map_location='cpu',weights_only=False)['model'];results[name]={}
  # All policies evaluated under identical original reward (same physics/actions).
  for graft in ['none','first_layer']:
   state={k:initial[k] if graft=='first_layer' and k.startswith('body.0.') else v for k,v in saved.items()}
   model=Policy('d4_exact',128).cuda();model.load_state_dict(state)
   results[name][graft]=ec.evaluate(model,base,corpus,128)
   print(name,graft,json.dumps(results[name][graft]),flush=True)
   (ROOT/'results/autoregressive-update-repair.json').write_text(json.dumps(dict(results=results,seconds=time.monotonic()-start),indent=2)+'\n')
if __name__=='__main__':main()
