"""Check source geometry, hidden-state isolation, history, CPU/CUDA parity."""
import ctypes as C,json,hashlib
import numpy as np
import torch
from runtime import Env,OUT,old,build
def save_json(path,x):path.write_text(json.dumps(x,indent=2))

def main():
    torch.set_num_threads(1);build();seen=set();maps=0
    for split in ['train','validation','test','long']:
        z=np.load(OUT/'maps'/f'{split}.npz')
        for f in z['floor']:
            h=hashlib.sha256(f.tobytes()).hexdigest();assert h not in seen,(split,h);seen.add(h);maps+=1
    e=Env('validation',12);ix=torch.tensor([0,1,2,3,4,5,256,257,258,259,260,261],device='cuda');e.reset(ix,91)
    a={k:v.cpu().contiguous() for k,v in e.arrays.items()};pr=e.profiles.cpu();ass=e.assign.cpu()
    table=old.Tables(pr.data_ptr(),ass.data_ptr(),1,0,e.batch,*[a[k].data_ptr() for k in ['floor','cells','index','distance']],int(a['ncells'][0]),a['ncells'].data_ptr(),a['offsets'].data_ptr(),len(a['floor']),-1,a['los'].data_ptr())
    state=torch.empty_like(e.state,device='cpu');memory=torch.empty_like(e.memory,device='cpu');grid=torch.empty_like(e.grid,device='cpu');mask=torch.empty_like(e.mask,device='cpu');stats=torch.empty_like(e.stats,device='cpu');labels=torch.empty_like(e.labels,device='cpu');out=torch.zeros_like(e.out,device='cpu');active=torch.ones(e.batch,dtype=torch.bool);ids=ix.int().cpu()
    lib=e.lib;p=C.c_void_p;i=C.c_int
    lib.grid_cpu_init.argtypes=[p,p,i,p,p,p,p,C.c_uint64];lib.grid_cpu_export.argtypes=[p,p,i,p,p,p,p,p];lib.grid_cpu_step.argtypes=[p,p,i,p,p,p,p,i,p];lib.grid_cpu_semantics.argtypes=[p,p,p]
    lib.grid_cpu_init(state.data_ptr(),memory.data_ptr(),e.batch,C.byref(e.config),C.byref(table),a['scenarios'].data_ptr(),ids.data_ptr(),91)
    comparisons=0
    for step in range(256):
        lib.grid_cpu_export(state.data_ptr(),memory.data_ptr(),e.batch,C.byref(table),grid.data_ptr(),mask.data_ptr(),stats.data_ptr(),labels.data_ptr())
        for cpu,gpu in [(grid,e.grid),(mask,e.mask),(stats,e.stats),(labels,e.labels),(memory,e.memory)]:assert torch.equal(cpu,gpu.cpu()),(step,cpu.shape)
        for j in range(e.batch):assert lib.grid_cpu_semantics(state[j].data_ptr(),memory[j].data_ptr(),C.byref(table))==1
        actions=labels.clone();lib.grid_cpu_step(state.data_ptr(),memory.data_ptr(),e.batch,C.byref(e.config),C.byref(table),actions.data_ptr(),active.data_ptr(),256,out.data_ptr());e.step(actions.cuda(),256)
        assert torch.equal(out,e.out.cpu());comparisons+=int(active.sum());active&=~out[:,1].bool()
        if not active.any():break
    assert not active.any()
    # Pressure: one backward step puts the last-seen marker outside the local
    # crop. Removing it leaves local observation identical, global different.
    e.reset(ix,91);a=e.labels.clone();e.step(a);g=e.grid.cpu();npaired=0
    for j in range(6,12):
        assert not (g[j,10].bool()&g[j,3].bool()).any()
        assert g[j,10].sum()>0
        x,y=e.stats[j,2:4].int().tolist();clean=g[j].clone();clean[6:]=0
        x0,x1=max(0,x-7),min(32,x+8);y0,y1=max(0,y-7),min(32,y+8)
        assert torch.equal(g[j,:,y0:y1,x0:x1],clean[:,y0:y1,x0:x1]);assert not torch.equal(g[j],clean);npaired+=1
    report=dict(distinct_layouts=maps,cpu_cuda_transitions=comparisons,hidden_state_checks=12*(step+1),out_of_view_memory_pairs=npaired,passed=True)
    save_json(OUT/'semantics.json',report);print(json.dumps(report))
if __name__=='__main__':main()
