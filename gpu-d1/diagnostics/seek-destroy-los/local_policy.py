"""LOS-only seek/destroy with persistent observed terrain and frontier guidance."""
import ctypes as C,hashlib,pathlib,subprocess
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
class LocalPolicy:
 def __init__(self,env,side,rest=False):
  self.env,self.side,self.rest=env,side,rest
  source=pathlib.Path(__file__).with_suffix('.cu');digest=hashlib.sha256(source.read_bytes()).hexdigest()
  directory=ROOT/'learning-runs/seek-destroy-los-assets';directory.mkdir(exist_ok=True)
  target=directory/f'local-{digest[:16]}.so'
  if not target.exists():subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',str(source),'-o',str(target)],check=True)
  self.lib=C.CDLL(str(target));self.lib.local_seek.argtypes=[C.c_void_p]*6+[C.c_int]*5+[C.c_void_p]
  self.memory=torch.zeros((env.batch,5600),dtype=torch.int8,device='cuda')
  self.actions=torch.full((env.batch,),8,dtype=torch.int64,device='cuda');self.reason=torch.zeros(env.batch,dtype=torch.int32,device='cuda')
 def __call__(self,active):
  e=self.env
  code=self.lib.local_seek(e.obs.data_ptr(),e.mask.data_ptr(),self.memory.data_ptr(),self.actions.data_ptr(),self.reason.data_ptr(),active.data_ptr(),e.batch,e.obs.shape[1],self.side,e.mask.shape[1],int(self.rest),e.stream)
  if code:raise RuntimeError(f'local policy CUDA error {code}')
  return self.actions
