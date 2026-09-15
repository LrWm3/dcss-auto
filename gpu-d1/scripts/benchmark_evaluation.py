"""Time the fixed 32-map/1024-episode panel, retaining terminal outcomes."""
import argparse,json,pathlib,time
import torch
from torch.distributions import Distribution
from benchmark_pipeline import Policy
from learn_env_ring_multi import Env
from learn_env import ROOT
ap=argparse.ArgumentParser();ap.add_argument('--library',type=pathlib.Path,required=True);ap.add_argument('--active',action='store_true');ap.add_argument('--output',type=pathlib.Path,required=True);args=ap.parse_args()
torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False;Distribution.set_default_validate_args(False)
ev=Env(1024,40,corpus=ROOT/'fixtures/d1-corpus-388/validation',map_limit=32,map_filter=-2,library_path=args.library)
saved=torch.load(ROOT/'learning-runs/ring-route-cue-corrected-200m-seed0/runs/route_cue-seed0/latest.pt',map_location='cpu',weights_only=False)
model=Policy(ev.obs.shape[1],ev.mask.shape[1]).cuda();model.load_state_dict(saved['model']);del saved
rows=[]
with torch.no_grad():
 for repeat in range(3):
  ev.reset(900000);torch.manual_seed(900000)
  active=torch.ones(ev.batch,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(ev.out);returns=torch.zeros(ev.batch,device='cuda')
  torch.cuda.synchronize();start=time.perf_counter()
  for _ in range(1024):
   dist,_=model(ev.obs,ev.mask);action=dist.sample()
   _,out=ev.step(action,active=active if args.active else None)
   returns+=active*out[:,0];ended=active & (out[:,1]>0);terminal[ended]=out[ended];active &= ~ended
  torch.cuda.synchronize();seconds=time.perf_counter()-start
  assert not active.any().item()
  rows.append(dict(seconds=seconds,clear_rate=terminal[:,2].mean().item(),death_rate=terminal[:,6].mean().item(),kills=terminal[:,3].mean().item()))
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(dict(library=str(args.library),active=args.active,rows=rows),indent=2)+'\n')
print(json.dumps(rows))
