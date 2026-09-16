"""Fuse recentering, all D4 transforms, padding and channels-last output."""
import ctypes as C,hashlib,pathlib,subprocess
import torch
_LIB=None

def library():
 global _LIB
 if _LIB is None:
  branch=pathlib.Path(__file__).resolve().parents[1];source=branch/'src/fast_maps.cu'
  work=branch.parents[1]/'learning-runs/centered-map-assets';work.mkdir(parents=True,exist_ok=True)
  path=work/'fast_maps.so';stamp=path.with_suffix('.sha256');digest=hashlib.sha256(source.read_bytes()).hexdigest()
  if not path.exists() or not stamp.exists() or stamp.read_text()!=digest:
   subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',str(source),'-o',str(path)],check=True);stamp.write_text(digest)
  _LIB=C.CDLL(str(path));_LIB.encode_maps.argtypes=[C.c_void_p]*3+[C.c_int]*3+[C.c_void_p]
 return _LIB

def spatial(obs,dtype=torch.float32):
 n=obs.shape[0];records=obs[:,450:650].reshape(n,40,5)
 px=(obs[:,652]*80).round().long();py=(obs[:,653]*70).round().long()
 x=(records[:,:,0]*80).round().long()+px[:,None]
 y=(records[:,:,1]*70).round().long()+py[:,None]
 indices=(y*80+x).clamp(0,5599)
 enemies=torch.zeros((n,2,5600),device=obs.device,dtype=obs.dtype)
 enemies[:,0].scatter_add_(1,indices,records[:,:,2]*records[:,:,4])
 enemies[:,1].scatter_add_(1,indices,obs[:,959:999]*records[:,:,4])
 out=torch.empty((n*8,3,160,160),device=obs.device,dtype=dtype,memory_format=torch.channels_last)
 code=library().encode_maps(obs.data_ptr(),enemies.data_ptr(),out.data_ptr(),n,obs.stride(0),dtype==torch.float16,torch.cuda.current_stream().cuda_stream)
 if code:raise RuntimeError(f'Fused map construction failed: {code}')
 return out
