"""Two-scale symbolic navigation, with an optional recurrent state."""
import torch
from torch import nn
from torch.nn import functional as F
from compact_policy import crop

def categories(grid):
    floor=grid[:,0:1]>0;wall=grid[:,1:2]>0;visited=(grid[:,2:3]>0)&floor
    return torch.cat([~(floor|wall),wall,floor&~visited,visited],1).float()

def global_map(grid,stats):
    n,_,h,w=grid.shape;device=grid.device
    yy,xx=torch.meshgrid(torch.arange(h,device=device),torch.arange(w,device=device),indexing='ij')
    bins=((yy*16//h)*16+xx*16//w).flatten()
    counts=torch.bincount(bins,minlength=256).clamp_min(1).float()
    values=torch.cat([categories(grid),(grid[:,4:5]>0).float()],1).flatten(2)
    out=values.new_zeros(n,6,256)
    out[:,:5].scatter_add_(2,bins[None,None].expand(n,5,-1),values)
    out[:,:4]/=counts[None,None]
    out[:,4].clamp_(0,1) # Sparse stairs are presence, not diluted occupancy.
    bx=(stats[:,2].long()*16//w).clamp(0,15);by=(stats[:,3].long()*16//h).clamp(0,15)
    out[:,5].scatter_(1,(by*16+bx)[:,None],1)
    return out.reshape(n,6,16,16)

class SymbolicPolicy(nn.Module):
    def __init__(self,recurrent=False):
        super().__init__();self.recurrent=recurrent
        yy,xx=torch.meshgrid(torch.arange(-7,8),torch.arange(-7,8),indexing='ij')
        self.register_buffer('offsets',torch.stack([xx,yy],-1)[None],persistent=False)
        def cnn(ch,out):
            return nn.Sequential(nn.Conv2d(ch,16,3,padding=1),nn.ReLU(),nn.Conv2d(16,24,3,stride=2,padding=1),nn.ReLU(),nn.Conv2d(24,24,3,stride=2,padding=1),nn.ReLU(),nn.AdaptiveAvgPool2d(4),nn.Flatten(),nn.Linear(24*16,out),nn.ReLU())
        self.local=cnn(5,64);self.global_net=cnn(6,96);self.tactical=cnn(6,32)
        self.core=nn.GRUCell(194,128) if recurrent else nn.Sequential(nn.Linear(194,128),nn.ReLU())
        self.policy=nn.Linear(128,19);self.value=nn.Linear(128,1)
        nn.init.zeros_(self.value.weight);nn.init.zeros_(self.value.bias)
    def encode(self,g,s,intervene=None):
        nav=torch.cat([categories(g),(g[:,4:5]>0).float()],1)
        local=crop(nav,s[:,2:4],self.offsets)
        # The finite map boundary is impassable, not undiscovered terrain.
        local[:,1:2]+=(local[:,:4].sum(1,keepdim=True)==0).float()
        visible=g[:,3:4].float()/255
        tactical=crop(torch.cat([visible,g[:,6:].float()/255*visible],1),s[:,2:4],self.offsets)
        glob=self.global_net(global_map(g,s))
        if intervene=='erase_global':glob=torch.zeros_like(glob)
        return torch.cat([self.local(local),glob,self.tactical(tactical),s[:,:2]],1)
    def step_features(self,x,mask,h=None):
        if self.recurrent:
            if h is None:h=x.new_zeros(len(x),128)
            z=self.core(x,h)
        else:z=self.core(x)
        return self.policy(z).float().masked_fill(mask==0,-1e9),z
    def forward(self,g,m,s,intervene=None):
        return self.step_features(self.encode(g,s,intervene),m)[0]

class Stateful:
    def __init__(self,model,reset_each_step=False):self.model=model;self.reset_each_step=reset_each_step;self.reset_cache()
    def reset_cache(self):self.hidden=None
    @torch.no_grad()
    def __call__(self,g,m,s,intervene=None):
        x=self.model.encode(g,s,intervene)
        logits,h=self.model.step_features(x,m,None if self.reset_each_step else self.hidden)
        self.hidden=h
        return logits
