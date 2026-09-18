"""Exact remembered geometry, position-dependent readout, inference-only cache.

The coarse pretrained branch is retained as a control/warm start. No routes,
frontiers, hidden terrain, or enemy locations enter the new map branch.
"""
import torch
from torch import nn
from torch.nn import functional as F
from native_remedies import ExactPolicy, SOURCE


class SpatialMap(nn.Module):
    def __init__(self):
        super().__init__()
        # Space-to-depth preserves every input tile, unlike occupancy pooling.
        self.net = nn.Sequential(nn.PixelUnshuffle(2), nn.Conv2d(20,16,3,padding=1),nn.ReLU(),
                                 nn.Conv2d(16,16,3,padding=2,dilation=2),nn.ReLU(),
                                 nn.Conv2d(16,8,3,padding=4,dilation=4),nn.ReLU())
        self.summary = nn.Linear(8*35*40,64)
    def forward(self,terrain):
        spatial=self.net(terrain.float())
        return spatial, self.summary(spatial.flatten(1))


class CachedExactPolicy(ExactPolicy):
    def __init__(self):
        super().__init__()
        del self.exact
        self.map_encoder=SpatialMap().to(memory_format=torch.channels_last)
        self.map_readout=nn.Sequential(nn.Linear(64+8*3*3+2,96),nn.ReLU(),nn.Linear(96,96))
        nn.init.zeros_(self.map_readout[-1].weight);nn.init.zeros_(self.map_readout[-1].bias)
        dy,dx=torch.meshgrid(torch.arange(-1,2),torch.arange(-1,2),indexing='ij')
        self.register_buffer('read_offsets',torch.stack([dx,dy],-1).reshape(1,9,2),persistent=False)

    def map_features(self,exact):
        return self.map_encoder(self._layout(exact[:,:5]))

    def read_map(self,exact,features):
        spatial,summary=features
        pos=exact[:,5].flatten(1).argmax(1)
        x=pos%80;y=pos//80
        xy=torch.stack([x//2,y//2],1)[:,None]+self.read_offsets
        valid=(xy[:,:,0]>=0)&(xy[:,:,0]<40)&(xy[:,:,1]>=0)&(xy[:,:,1]<35)
        idx=xy[:,:,1].clamp(0,34)*40+xy[:,:,0].clamp(0,39)
        patch=spatial.flatten(2).gather(2,idx[:,None].expand(-1,8,-1))*valid[:,None]
        position=torch.stack([x/79.,y/69.],1)
        return self.map_readout(torch.cat([summary,patch.flatten(1),position],1))

    def encode_with_map(self,inputs,features,intervene=None):
        local,exact,tactical,stats=inputs;exact=exact.float();n=len(exact)
        glob=exact.new_zeros(n,6,256)
        glob.scatter_add_(2,self.exact_bins[None,None].expand(n,6,-1),exact.flatten(2))
        glob=torch.cat([glob[:,:4]/self.exact_counts[None,None],glob[:,4:].clamp(0,1)],1).reshape(n,6,16,16)
        residual=self.read_map(exact,features)
        if intervene=='erase_exact':residual=torch.zeros_like(residual)
        global_features=self.global_net(self._layout(glob))+residual
        return torch.cat([self.local(self._layout(local)),global_features,self.tactical(self._layout(tactical)),stats],1)

    def encode_prepared(self,inputs,intervene=None):
        return self.encode_with_map(inputs,self.map_features(inputs[1]),intervene)


def make_model():
    model=CachedExactPolicy().cuda()
    missing,unexpected=model.load_state_dict(torch.load(SOURCE,weights_only=False)['model'],strict=False)
    assert not unexpected and all(k.startswith(('map_encoder.','map_readout.')) for k in missing)
    return model


class CachedInference:
    """Exact refresh; caches never cross resets or parameter updates.

    Training always recomputes features with autograd and current weights.
    Tensor version checks additionally invalidate inference caches after updates.
    """
    def __init__(self,model,cache=True,compiled_readout=False):
        self.model=model;self.cache=cache;self.refreshes=0;self.observations=0
        self.readout=model.encode_with_map
        if compiled_readout:
            self.readout=torch.compile(self.readout,fullgraph=True,dynamic=False,options={'triton.cudagraphs':False})
        self.reset_cache()
    def reset_cache(self):
        self.hidden=None;self.snapshot=None;self.features=None;self.versions=None
    @torch.no_grad()
    def __call__(self,g,mask,s,intervene=None):
        p=self.model.prepare(g,s);terrain=p[1][:,:5].to(torch.uint8)
        versions=tuple(v._version for v in self.model.map_encoder.parameters())
        fresh=self.snapshot is None or self.snapshot.shape!=terrain.shape or versions!=self.versions
        with torch.autocast('cuda',dtype=torch.float16):
            if fresh or not self.cache:
                self.features=self.model.map_features(p[1]);self.snapshot=terrain.clone();count=len(g)
            else:
                ids=(terrain!=self.snapshot).flatten(1).any(1).nonzero().flatten();count=len(ids)
                if count:
                    updated=self.model.map_features(p[1][ids])
                    for dst,src in zip(self.features,updated):dst[ids]=src
                    self.snapshot[ids]=terrain[ids]
            self.versions=versions;self.refreshes+=count;self.observations+=len(g)
            x=self.readout(p,self.features,intervene)
            logits,self.hidden=self.model.step_features(x,mask,self.hidden)
        return logits
