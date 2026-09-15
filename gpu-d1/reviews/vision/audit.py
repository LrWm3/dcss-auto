"""Replay final checkpoints and audit sampled world states without modifying runs."""
import ctypes as C
import json
import pathlib
import sys
import torch
from torch import nn
from torch.distributions import Categorical

SHARED=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SHARED/'branches/vision-v1/scripts'))
from learn_env_ring_multi import Env
from run_ring_ablations import library_key

torch.set_num_threads(1);torch.distributions.Distribution.set_default_validate_args(False)
torch.backends.cuda.matmul.allow_tf32=False
suite=SHARED/'learning-runs/vision24-512-screen-30m'
manifest=json.loads((suite/'manifest.json').read_text())
audit=C.CDLL(sys.argv[1]);audit.audit.argtypes=[C.c_void_p,C.c_int,C.c_void_p,C.c_void_p,C.c_int,C.c_void_p]
class Policy(nn.Module):
 def __init__(self):
  super().__init__();self.body=nn.Sequential(nn.Linear(502,128),nn.Tanh(),nn.Linear(128,128),nn.Tanh());self.actor=nn.Linear(128,9);self.critic=nn.Linear(128,1)
 def forward(self,obs,mask):return Categorical(logits=self.actor(self.body(obs)).masked_fill(mask==0,-1e9))
rows=[]
with torch.no_grad():
 for job in manifest['jobs']:
  args=dict(batch=1024,enemies=24,seed=900000,map_filter=-2,limit=512,map_limit=32,
            corpus=SHARED/'fixtures/d1-corpus-388/validation',library_path=suite/'build'/(library_key(job)+'.so'))
  gpu=Env(device='cuda',**args);args['batch']=1;cpu=Env(device='cpu',**args)
  saved=torch.load(suite/'runs'/job['id']/'latest.pt',map_location='cpu',weights_only=False)
  model=Policy().cuda();model.load_state_dict(saved['model']);model.eval()
  torch.manual_seed(900000);active=torch.ones(1024,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(gpu.out)
  errors=(C.c_int*10)();snapshots=0
  for step in range(512):
   if step%32==0:
    start=(step//32)*64
    states=gpu.state[start:start+64].cpu();obs=gpu.obs[start:start+64].cpu()
    audit.audit(states.data_ptr(),64,C.byref(cpu.tables),obs.data_ptr(),job['terrain_los'],C.addressof(errors));snapshots+=64
   action=model(gpu.obs,gpu.mask).sample();_,out=gpu.step(action,active=active)
   ended=active&(out[:,1]>0);terminal[ended]=out[ended];active&=~ended
  assert not active.any()
  final=json.loads((suite/'runs'/job['id']/'result.json').read_text())['final']['sampled']
  assert float(terminal[:,2].mean())==final['clear_rate']
  row=dict(job=job['id'],snapshots=snapshots,errors=list(errors),clear_rate=float(terminal[:,2].mean()),matched_final_clear_rate=True)
  rows.append(row);print(json.dumps(row),flush=True)
  del gpu,cpu,model,saved
assert all(not any(r['errors']) for r in rows)
(SHARED/'reviews/vision/audit-results.json').write_text(json.dumps(rows,indent=2)+'\n')
