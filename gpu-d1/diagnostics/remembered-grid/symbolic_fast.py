"""Equivalent symbolic preprocessing and fused sequence GRU execution."""
import torch
from torch import nn
from symbolic_policy import SymbolicPolicy,categories
from compact_policy import crop

class FastSymbolicPolicy(SymbolicPolicy):
    def __init__(self,recurrent=True):
        super().__init__(recurrent);self._bins={}
        if recurrent:
            self.sequence_core=nn.GRU(194,128,batch_first=True)
            # Share the original parameters: no frozen layers or extra capacity.
            for name in ['weight_ih','weight_hh','bias_ih','bias_hh']:
                setattr(self.sequence_core,name+'_l0',getattr(self.core,name))
    def prepare(self,g,s):
        n,_,h,w=g.shape;raw=crop(g,s[:,2:4],self.offsets)
        nav=torch.cat([categories(raw),(raw[:,4:5]>0).float()],1)
        xy=s[:,None,None,2:4].long()+self.offsets
        valid=((xy[...,0]>=0)&(xy[...,0]<w)&(xy[...,1]>=0)&(xy[...,1]<h))[:,None]
        nav[:,0:1]*=valid;nav[:,1:2]=torch.where(valid,nav[:,1:2],1.)
        visible=raw[:,3:4].float()/255
        tactical=torch.cat([visible,raw[:,6:].float()/255*visible],1)
        key=(h,w,g.device)
        if key not in self._bins:
            yy,xx=torch.meshgrid(torch.arange(h,device=g.device),torch.arange(w,device=g.device),indexing='ij')
            bins=((yy*16//h)*16+xx*16//w).flatten();counts=torch.bincount(bins,minlength=256).clamp_min(1).float()
            self._bins[key]=(bins,counts)
        bins,counts=self._bins[key]
        vals=torch.cat([categories(g),(g[:,4:5]>0).float()],1).flatten(2);glob=vals.new_zeros(n,6,256)
        glob[:,:5].scatter_add_(2,bins[None,None].expand(n,5,-1),vals);glob[:,:4]/=counts[None,None];glob[:,4].clamp_(0,1)
        bx=(s[:,2].long()*16//w).clamp(0,15);by=(s[:,3].long()*16//h).clamp(0,15);glob[:,5].scatter_(1,(by*16+bx)[:,None],1)
        return nav,glob.reshape(n,6,16,16),tactical,s[:,:2]
    def encode_prepared(self,inputs,intervene=None):
        nav,glob,tactical,stats=inputs;glob=self.global_net(glob)
        if intervene=='erase_global':glob=torch.zeros_like(glob)
        return torch.cat([self.local(nav),glob,self.tactical(tactical),stats],1)
    def encode(self,g,s,intervene=None):return self.encode_prepared(self.prepare(g,s),intervene)
    def sequence(self,x,h=None):
        # Input is [batch,time,features]. Padding must be handled by the caller.
        z,h=self.sequence_core(x,None if h is None else h[None].contiguous())
        return z,h[0]
