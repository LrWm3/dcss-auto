"""Replay the final travel policy and measure selected vs completed trip lengths."""
import json
from pathlib import Path
import sys
import torch
from torch import nn
from torch.distributions import Categorical,Distribution
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'branches/vision-frontier-travel-v1/scripts'))
from learn_env_ring_multi import Env
from run_ring_ablations import library_key
suite=root/'learning-runs/vision-frontier-travel-30m'
r=json.loads((suite/'runs/ogre2_wake_los-seed0/result.json').read_text());job=r['job']
torch.set_num_threads(1);Distribution.set_default_validate_args(False)
env=Env(batch=1024,enemies=26,seed=900000,corpus=root/'fixtures/d1-corpus-388/validation',map_limit=32,map_filter=-2,limit=512,library_path=suite/'build'/(library_key(job)+'.so'))
class Policy(nn.Module):
    def __init__(self):
        super().__init__();self.body=nn.Sequential(nn.Linear(502,128),nn.Tanh(),nn.Linear(128,128),nn.Tanh());self.actor=nn.Linear(128,10);self.critic=nn.Linear(128,1)
    def forward(self,obs,mask):
        return Categorical(logits=self.actor(self.body(obs)).masked_fill(mask==0,-1e9))
model=Policy().cuda();saved=torch.load(suite/'runs/ogre2_wake_los-seed0/latest.pt',map_location='cpu',weights_only=False);model.load_state_dict(saved['model']);del saved
active=torch.ones(1024,dtype=torch.bool,device='cuda');clears=torch.zeros(1024,device='cuda');records=[]
torch.manual_seed(900000)
with torch.no_grad():
    for step in range(512):
        planned=(env.obs[:,409]*150).round()
        action=model(env.obs,env.mask).sample()
        chosen=active & (action==9)
        env.step(action,active=active)
        out=env.out
        records.append(torch.stack([planned,out[:,26],out[:,29],out[:,30]],1)[chosen].clone())
        ended=active & (out[:,1]>0);clears[ended]=out[ended,2];active&=~ended
assert not active.any()
assert clears.mean().item()==r['final']['sampled']['clear_rate']
a=torch.cat(records).cpu();planned,actual,arrival,interrupt=a.T
summary=dict(trips=len(a),clear_rate=clears.mean().item(),planned_mean=planned.mean().item(),actual_mean=actual.mean().item(),planned_median=planned.median().item(),planned_p90=torch.quantile(planned,.9).item(),planned_max=planned.max().item(),planned_at_most_3=(planned<=3).float().mean().item(),planned_at_most_4=(planned<=4).float().mean().item(),interrupt_fraction=interrupt.mean().item(),arrival_fraction=arrival.mean().item(),interrupted_planned_mean=planned[interrupt>0].mean().item(),interrupted_actual_mean=actual[interrupt>0].mean().item(),completed_mean=actual[arrival>0].mean().item(),planned_histogram={str(i):int((planned==i).sum()) for i in range(1,9)},planned_above8=int((planned>8).sum()))
(root/'results/vision-frontier-travel-lengths.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
