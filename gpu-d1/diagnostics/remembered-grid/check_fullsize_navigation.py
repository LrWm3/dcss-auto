"""Full-size CPU/CUDA parity and native-corpus integrity before PPO use."""
import ctypes as C,hashlib,json
import numpy as np
import torch
from fullsize_navigation import FullEnv,FOLDER,build_full
from run import evaluate,save_json
from runtime import ROOT,old

def main():
 torch.set_num_threads(1);build_full();seen=set();maps=0
 for split in ('train','validation','test'):
  with np.load(FOLDER/'maps'/f'{split}.npz') as a:
   assert a['floor'].shape[1]==5600
   for f in a['floor']:
    h=hashlib.sha256(f.tobytes()).hexdigest();assert h not in seen;seen.add(h);maps+=1
   for row in a['scenarios']:
    mid,kind,player,*_=row;n=int(a['ncells'][mid]);off=int(a['offsets'][mid]);hist=row[8:8+row[7]]
    assert hist[-1]==player and all(a['floor'][mid,p] for p in hist)
    assert all(max(abs(int(p)%80-int(q)%80),abs(int(p)//80-int(q)//80))==1 for p,q in zip(hist,hist[1:]))
    assert row[6]==-1 and all(a['floor'][mid,p] for p in row[3:6])
    if kind==0:assert hist[0] in row[3:6]
 e=FullEnv('validation',8);ix=torch.arange(8,device='cuda')*9;e.reset(ix,91)
 assert len(e.scenes[ix,0].unique())==8
 a={k:v.cpu().contiguous() for k,v in e.arrays.items()};pr=e.profiles.cpu();ass=e.assign.cpu()
 table=old.Tables(pr.data_ptr(),ass.data_ptr(),1,0,e.batch,*[a[k].data_ptr() for k in ['floor','cells','index','distance']],int(a['ncells'][0]),a['ncells'].data_ptr(),a['offsets'].data_ptr(),len(a['floor']),-1,a['los'].data_ptr())
 state=torch.empty_like(e.state,device='cpu');memory=torch.empty_like(e.memory,device='cpu');grid=torch.empty_like(e.grid,device='cpu');mask=torch.empty_like(e.mask,device='cpu');stats=torch.empty_like(e.stats,device='cpu');labels=torch.empty_like(e.labels,device='cpu');out=torch.zeros_like(e.out,device='cpu');active=torch.ones(e.batch,dtype=torch.bool);ids=ix.int().cpu()
 lib=e.lib;p=C.c_void_p;i=C.c_int
 lib.grid_cpu_init.argtypes=[p,p,i,p,p,p,p,C.c_uint64];lib.grid_cpu_export.argtypes=[p,p,i,p,p,p,p,p];lib.grid_cpu_step.argtypes=[p,p,i,p,p,p,p,i,p];lib.grid_cpu_semantics.argtypes=[p,p,p]
 lib.grid_cpu_init(state.data_ptr(),memory.data_ptr(),e.batch,C.byref(e.config),C.byref(table),a['scenarios'].data_ptr(),ids.data_ptr(),91)
 comparisons=0
 for tick in range(1024):
  lib.grid_cpu_export(state.data_ptr(),memory.data_ptr(),e.batch,C.byref(table),grid.data_ptr(),mask.data_ptr(),stats.data_ptr(),labels.data_ptr())
  for cpu,gpu in [(grid,e.grid),(mask,e.mask),(stats,e.stats),(labels,e.labels),(memory,e.memory)]:assert torch.equal(cpu,gpu.cpu()),(tick,cpu.shape)
  for j in range(e.batch):assert lib.grid_cpu_semantics(state[j].data_ptr(),memory[j].data_ptr(),C.byref(table))==1
  action=labels.clone();lib.grid_cpu_step(state.data_ptr(),memory.data_ptr(),e.batch,C.byref(e.config),C.byref(table),action.data_ptr(),active.data_ptr(),1024,out.data_ptr());e.step(action.cuda(),1024)
  assert torch.equal(out,e.out.cpu());comparisons+=int(active.sum());active&=~out[:,1].bool()
  if not active.any():break
 assert not active.any()
 teacher=evaluate(None,'validation',teacher=True,env_class=FullEnv,limit=1024)
 assert teacher['summary']['known_stairs']['exit']>=.95, 'Known-goal controller failed viability check'
 assert teacher['summary']['exploration']['exit']>=.90, 'Exploration controller failed viability check'
 result=dict(passed=True,distinct_maps=maps,parity_layouts=8,cpu_cuda_transitions=comparisons,observation_shape=list(e.grid.shape[1:]),teacher_validation=teacher)
 save_json(ROOT/'results/symbolic-fullsize-preflight.json',result);print(json.dumps({k:v for k,v in result.items() if k!='teacher_validation'}));print(teacher['summary'])
if __name__=='__main__':main()
