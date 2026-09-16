"""One retreat attempt per visible encounter, using observed hallways only."""
import ctypes as C,hashlib,pathlib,subprocess
import torch
from local_policy import LocalPolicy,ROOT
EVENTS=['starts','arrivals','enemy_blocks','hold_waits','retreat_steps','adjacent_resumptions','visibility_resets','no_hall_decisions','route_aborts','lockout_decisions','inferred_enemy_blocks']
class RetreatPolicy:
 def __init__(self,env,privileged=False,enabled=True,wait_for_awake=False):
  if env.obs.shape[1]!=999:raise ValueError('Retreat requires the 15x15 visible sleep-status observation')
  self.wait_for_awake=wait_for_awake
  self.env,self.privileged,self.enabled=env,privileged,enabled;self.base=LocalPolicy(env,15,True)
  source=pathlib.Path(__file__).with_suffix('.cu');digest=hashlib.sha256(source.read_bytes()).hexdigest()
  target=ROOT/'learning-runs/seek-destroy-los-assets'/f'retreat-{digest[:16]}.so'
  if not target.exists():subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',str(source),'-o',str(target)],check=True)
  self.lib=C.CDLL(str(target));self.lib.hallway_retreat.argtypes=[C.c_void_p]*7+[C.c_int]*4+[C.c_void_p]
  self.state=torch.zeros((env.batch,2),dtype=torch.int32,device='cuda')
  self.events=torch.zeros((env.batch,len(EVENTS)),dtype=torch.int32,device='cuda')
 def overlay(self,actions,active):
  e=self.env
  code=self.lib.hallway_retreat(e.obs.data_ptr(),e.mask.data_ptr(),self.base.memory.data_ptr(),actions.data_ptr(),self.state.data_ptr(),self.events.data_ptr(),active.data_ptr(),e.batch,e.obs.shape[1],15,e.mask.shape[1],e.stream)
  if code:raise RuntimeError(f'retreat policy CUDA error {code}')
  return actions
 def __call__(self,active):
  actions=self.base(active).clone() # Also updates observed terrain memory.
  if self.privileged:actions=torch.where(self.env.mask[:,9]>0,9,self.env.heuristic()).clone()
  self.approach_wait=torch.zeros_like(active)
  if self.wait_for_awake:
   records=self.env.obs[:,450:650].reshape(-1,40,5)
   visible=records[:,:,4]>0
   awake=visible&(self.env.obs[:,959:999]<0)
   dx=(records[:,:,0]*80).round();dy=(records[:,:,1]*70).round()
   adjacent=(visible&(dx.abs()<=1)&(dy.abs()<=1)&((dx!=0)|(dy!=0))).any(-1)
   self.approach_wait=active&awake.any(-1)&~adjacent
   actions=torch.where(self.approach_wait,8,actions)
  self.before=self.env.obs[:,652:654].clone()
  if self.enabled:actions=self.overlay(actions,active)
  self.pending=(self.events[:,4]>0)&active if self.enabled else torch.zeros_like(active)
  self.approach_wait&=actions==8
  return actions
 def after_step(self,ended):
  # A failed step into known static floor implies enemy occupancy, even if
  # corner LOS hid it. Infer this only from the failed movement, never state.
  blocked=self.pending&~ended&(self.env.obs[:,652:654]==self.before).all(-1)
  self.state[blocked,0]=3;self.events[blocked,10]+=1
