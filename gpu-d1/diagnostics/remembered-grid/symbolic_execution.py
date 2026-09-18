"""Optional compiled encoders/heads and static CUDA-graph execution.

The cuDNN GRU stays eager. Graphs capture forward/backward, keeping Adam,
GradScaler overflow checks and gradient clipping outside capture. Inputs and
parameters must retain their storage; data and weights may change in place.
"""
import time
import torch
from symbolic_fast import FastSymbolicPolicy
from optimize_symbolic import inputs


class PolicyExecution:
    def __init__(self, model, compiled=False):
        self.model=model
        self.encode=model.encode_prepared
        self.heads=self._heads
        if compiled:
            # Manual graph capture is a separate experimental factor.
            options={'triton.cudagraphs':False}
            self.encode=torch.compile(self.encode,fullgraph=True,dynamic=False,options=options)
            self.heads=torch.compile(self.heads,fullgraph=True,dynamic=False,options=options)

    def _heads(self,z,mask):
        return self.model.policy(z).float().masked_fill(mask==0,-1e9),self.model.value(z).float().squeeze(-1)

    def features(self,g,s,prepared=None):
        return self.encode(self.model.prepare(g,s) if prepared is None else prepared)

    def infer(self,g,mask,s,h):
        x=self.features(g,s)
        z=self.model.core(x,h)
        logits,v=self.heads(z,mask)
        return logits,v,z


class StaticUpdate:
    def __init__(self,batch=256,amp=False,prepared=False,compiled=False,graphed=False):
        self.model=FastSymbolicPolicy(True,True,True).cuda()
        self.execution=PolicyExecution(self.model,compiled)
        self.opt=torch.optim.Adam(self.model.parameters(),lr=1e-5)
        self.scaler=torch.amp.GradScaler('cuda',enabled=amp)
        self.amp=amp;self.batch=batch;self.prepared=prepared;self.graphed=graphed
        self.g,self.mask,self.s=inputs(batch);self.gb,self.mb,self.sb=inputs(batch)
        self.p=self.pb=None
        if prepared:
            with torch.no_grad():self.p=self.model.prepare(self.g,self.s);self.pb=self.model.prepare(self.gb,self.sb)
        self.action=torch.zeros(batch,device='cuda',dtype=torch.long)
        self.oldlp=torch.full((batch,),-3.,device='cuda')
        self.adv=torch.randn(batch,device='cuda');self.ret=torch.randn(batch,device='cuda')
        self.graph=None;self.setup_seconds=0.

    def loss(self):
        n=self.batch//16
        # Separate contexts are essential: don't cache detached burn-in weights
        # for the learning encoder (the previous benchmark regression).
        with torch.no_grad(),torch.autocast('cuda',enabled=self.amp,dtype=torch.float16):
            burn=self.execution.features(self.gb,self.sb,self.pb).reshape(n,16,-1)
            _,h=self.model.sequence(burn)
        with torch.autocast('cuda',enabled=self.amp,dtype=torch.float16):
            x=self.execution.features(self.g,self.s,self.p).reshape(n,16,-1)
            z,_=self.model.sequence(x,h)
            logits,v=self.execution.heads(z.reshape(self.batch,128),self.mask)
        d=torch.distributions.Categorical(logits=logits,validate_args=False)
        ratio=(d.log_prob(self.action)-self.oldlp).exp()
        return -torch.minimum(ratio*self.adv,ratio.clamp(.8,1.2)*self.adv).mean()+.25*(v-self.ret).square().mean()-.001*d.entropy().mean()

    def backward(self):
        self.current_loss=self.loss()
        self.scaler.scale(self.current_loss).backward()

    def capture(self):
        start=time.perf_counter()
        stream=torch.cuda.Stream();stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream):
            for _ in range(3):
                self.opt.zero_grad(set_to_none=True);self.backward()
        torch.cuda.current_stream().wait_stream(stream)
        self.opt.zero_grad(set_to_none=True)
        self.graph=torch.cuda.CUDAGraph()
        with torch.cuda.graph(self.graph):self.backward()
        torch.cuda.synchronize();self.setup_seconds=time.perf_counter()-start

    def step(self):
        if self.graphed:
            if self.graph is None:self.capture()
            # Captured backward writes the same persistent .grad buffers anew.
            # Do not set those buffers to None between graph replays.
            self.graph.replay()
        else:
            self.opt.zero_grad(set_to_none=True);self.backward()
        self.scaler.unscale_(self.opt)
        torch.nn.utils.clip_grad_norm_(self.model.parameters(),.5)
        self.scaler.step(self.opt);self.scaler.update()


class StaticInference:
    """Stateful policy with fresh input copies on every graph replay."""
    def __init__(self,execution,amp=False,graphed=False):
        self.execution=execution;self.amp=amp;self.graphed=graphed
        self.graph=None;self.signature=None;self.reset_cache()

    def reset_cache(self):self.hidden=None

    def _run(self):
        with torch.autocast('cuda',enabled=self.amp,dtype=torch.float16):
            return self.execution.infer(self.g,self.mask,self.s,self.h)

    @torch.no_grad()
    def outputs(self,g,mask,s):
        if not self.graphed:
            if self.hidden is None:self.hidden=torch.zeros(len(g),128,device=g.device)
            with torch.autocast('cuda',enabled=self.amp,dtype=torch.float16):
                logits,v,self.hidden=self.execution.infer(g,mask,s,self.hidden)
            return logits,v
        signature=(tuple(g.shape),g.dtype,g.device)
        if self.signature!=signature:
            self.g=g.clone();self.mask=mask.clone();self.s=s.clone()
            self.h=torch.zeros(len(g),128,device=g.device)
            stream=torch.cuda.Stream();stream.wait_stream(torch.cuda.current_stream())
            with torch.cuda.stream(stream):
                for _ in range(3):self.result=self._run()
            torch.cuda.current_stream().wait_stream(stream)
            self.graph=torch.cuda.CUDAGraph()
            with torch.cuda.graph(self.graph):self.result=self._run()
            self.signature=signature;self.hidden=None
        self.g.copy_(g);self.mask.copy_(mask);self.s.copy_(s)
        if self.hidden is None:self.h.zero_()
        else:self.h.copy_(self.hidden)
        self.graph.replay()
        logits,v,self.hidden=self.result
        return logits,v

    def __call__(self,g,mask,s,intervene=None):
        if intervene is not None:raise ValueError('Interventions require the eager evaluator')
        return self.outputs(g,mask,s)[0]
