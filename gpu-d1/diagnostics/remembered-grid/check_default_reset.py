import sys,ctypes as C,subprocess,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import runtime as r
import torch
torch.set_num_threads(1)
out=r.OUT/'default-reset-check';out.mkdir(exist_ok=True)
subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*r.old.FLAGS,'-DCLUMP_MODE=0',str(r.old.HERE/'hooks.cu'),'-o',str(out/'stats-clump0.so')],check=True)
r.old.SUITE=out
e=r.old.Env(batch=1,device='cpu',map_limit=1,clump=0)
assert e.lib.stats_semantics(C.byref(e.config),C.byref(e.tables))==0
e.limit=1;e.step(torch.tensor([16],dtype=torch.long));meta=e.metadata_tensor()
assert e.out[0,7]==1 and meta[0,10]==0
(r.OUT/'default-reset-check.json').write_text(json.dumps(dict(default_reset_preserved=True,legacy_semantics_passed=True)))
print('PASS default reset and legacy semantics')
