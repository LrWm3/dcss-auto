"""CUDA-graph inference with fresh casts of mutable parameters on every replay."""
import torch

class GraphForward:
    def __init__(self,fn):self.fn=fn;self.cache={}
    @torch.no_grad()
    def __call__(self,*args):
        key=tuple((tuple(x.shape),x.dtype) for x in args)
        if key not in self.cache:
            inputs=[x.clone() for x in args];side=torch.cuda.Stream();side.wait_stream(torch.cuda.current_stream())
            with torch.cuda.stream(side):
                for _ in range(3):
                    with torch.autocast('cuda',dtype=torch.float16,cache_enabled=False):self.fn(*inputs)
            torch.cuda.current_stream().wait_stream(side)
            graph=torch.cuda.CUDAGraph()
            with torch.cuda.graph(graph):
                with torch.autocast('cuda',dtype=torch.float16,cache_enabled=False):outputs=self.fn(*inputs)
            self.cache[key]=(inputs,outputs,graph)
        inputs,outputs,graph=self.cache[key]
        for target,source in zip(inputs,args):target.copy_(source)
        graph.replay()
        # Rollout buffers must not alias buffers overwritten by subsequent replay.
        return tuple(x.clone() for x in outputs) if isinstance(outputs,tuple) else outputs.clone()

class GraphInference:
    def __init__(self,model):self.forward=GraphForward(model.raw)
    def __call__(self,x,mask):
        logits,value=self.forward(x,mask)
        return torch.distributions.Categorical(logits=logits,validate_args=False),value

class GPURouter:
    def __init__(self):
        import ctypes as C,hashlib,subprocess
        from pathlib import Path
        from route_threat_env import FOLDER_OUT
        source=Path(__file__).with_name('route_candidates_cuda.cu');lib=FOLDER_OUT/'gpu-routes.so';stamp=lib.with_suffix('.sha256');digest=hashlib.sha256(source.read_bytes()).hexdigest()
        if not lib.exists() or not stamp.exists() or stamp.read_text()!=digest:
            tmp=lib.with_suffix('.tmp.so');subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',str(source),'-o',str(tmp)],check=True);tmp.replace(lib);stamp.write_text(digest)
        self.lib=C.CDLL(str(lib));self.lib.gpu_routes.argtypes=[C.c_int,C.c_void_p,C.c_int]+[C.c_void_p]*6
    def __call__(self,g,mask):
        n=len(g);assert g.is_cuda and g.dtype==torch.uint8 and g.stride(-1)==1 and g.stride(-2)==80 and g.stride(1)==5600
        first=torch.empty(n,5600,device=g.device,dtype=torch.int8);cand=torch.empty(n,5600,device=g.device,dtype=torch.uint8);goal=torch.empty(n,device=g.device,dtype=torch.long);act=torch.empty_like(goal)
        error=self.lib.gpu_routes(n,g.data_ptr(),g.stride(0),mask.data_ptr(),first.data_ptr(),cand.data_ptr(),goal.data_ptr(),act.data_ptr(),torch.cuda.current_stream().cuda_stream)
        if error:raise RuntimeError(error)
        return first,cand,goal,act
