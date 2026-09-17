"""Player-independent remembered-terrain features and a cheap per-action policy."""
import torch
from torch import nn
from torch.nn import functional as F

class MapEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        def block(a,b):return nn.Sequential(nn.Conv2d(a,b,3,padding=1),nn.ReLU(),nn.Conv2d(b,b,3,padding=1),nn.ReLU())
        self.fine=block(3,16);self.middle=block(16,24);self.coarse=block(24,32)
        self.context=nn.Sequential(nn.Conv2d(32,32,3,padding=2,dilation=2),nn.ReLU(),nn.Conv2d(32,32,3,padding=2,dilation=2),nn.ReLU())
        self.up_middle=block(56,24);self.up_fine=block(40,16)
    def forward(self,terrain):
        g=terrain.float()/255.;fine=self.fine(g);middle=self.middle(F.max_pool2d(fine,2));coarse=self.coarse(F.max_pool2d(middle,2));context=self.context(coarse)
        middle=self.up_middle(torch.cat([middle,F.interpolate(context,size=middle.shape[-2:],mode='nearest')],1))
        return self.up_fine(torch.cat([fine,F.interpolate(middle,size=fine.shape[-2:],mode='nearest')],1))

class FastActor(nn.Module):
    def __init__(self):
        super().__init__()
        self.local=nn.Sequential(nn.Conv2d(11,16,3,padding=1),nn.ReLU(),nn.Conv2d(16,16,3,padding=1),nn.ReLU(),nn.Flatten(),nn.Linear(16*15*15,64),nn.ReLU())
        self.readout=nn.Sequential(nn.Linear(144,128),nn.ReLU())
        self.shared=nn.Sequential(nn.Linear(195,128),nn.ReLU())
        self.policy=nn.Linear(128,19);self.value=nn.Linear(128,1)
        nn.init.zeros_(self.value.weight);nn.init.zeros_(self.value.bias)
        with torch.no_grad():self.shared[0].weight[:,-1].zero_()
    def forward(self,local,features,scalars,mask):
        z=self.shared(torch.cat([self.local(local.float()/255.),self.readout(features.float()),scalars],1))
        return self.policy(z).float().masked_fill(mask==0,-1e9),self.value(z).float().squeeze(-1)

class CachedMapPolicy(nn.Module):
    def __init__(self,amp=False):
        super().__init__();self.encoder=MapEncoder();self.actor=FastActor();self.amp=amp
        yy,xx=torch.meshgrid(torch.arange(-7,8),torch.arange(-7,8),indexing='ij');self.register_buffer('local_xy',torch.stack([xx,yy],-1)[None].float(),persistent=False)
        yy,xx=torch.meshgrid(torch.arange(-1,2),torch.arange(-1,2),indexing='ij');self.register_buffer('read_xy',torch.stack([xx,yy],-1)[None].float(),persistent=False)
    @staticmethod
    def terrain(grid):return grid[:,[0,1,4]].contiguous()
    def inputs(self,grid,stats,feature_map,age=None):
        # Integer crops avoid converting the entire cached/full map every decision.
        def crop(x,offsets):
            h,w=x.shape[-2:];xy=stats[:,None,None,2:4].long()+offsets.long()
            valid=(xy[...,0]>=0)&(xy[...,0]<w)&(xy[...,1]>=0)&(xy[...,1]<h)
            index=(xy[...,1].clamp(0,h-1)*w+xy[...,0].clamp(0,w-1)).flatten(1)
            out=x.flatten(2).gather(2,index[:,None].expand(-1,x.shape[1],-1))
            return out.reshape(len(x),x.shape[1],*offsets.shape[1:3])*valid[:,None]
        local=crop(grid,self.local_xy).float()
        local=torch.cat([local[:,:6],local[:,6:]*(local[:,3:4]/255.)],1)
        features=crop(feature_map,self.read_xy).flatten(1).float()
        if age is None:age=torch.zeros(len(grid),device=grid.device)
        return local,features,torch.cat([stats[:,:2],age[:,None].clamp(max=32)/32],1)
    def forward(self,grid,mask,stats,intervene=None,terrain=None,age=None):
        with torch.autocast(grid.device.type,dtype=torch.float16,enabled=self.amp and grid.is_cuda):
            feature_map=self.encoder(self.terrain(grid) if terrain is None else terrain)
            local,features,scalars=self.inputs(grid,stats,feature_map,age)
            if intervene=='erase_global':features=torch.zeros_like(features)
            return self.actor(local,features,scalars,mask)[0]

class FeatureCache:
    """Per-world refresh on changes, interval, new stairs or 16 new terrain cells.

    Unchanged terrain reuses its features indefinitely. Age denotes staleness
    only when the map differs, not time spent holding an identical valid map.
    Call reset_cache at every environment reset. Cache is inference-only.
    """
    def __init__(self,model,interval=8,threshold=16):
        self.model=model;self.interval=interval;self.threshold=threshold;self.total_refreshes=0;self.total_encoded_slots=0;self.total_observations=0;self.reset_cache()
    def reset_cache(self):
        self.snapshot=None;self.features=None;self.age=None;self.refreshes=0;self.observations=0
    @torch.no_grad()
    def prepare(self,grid,stats):
        terrain=self.model.terrain(grid);n=len(grid)
        if self.snapshot is None:
            self.snapshot=torch.zeros_like(terrain);self.features=torch.empty(n,16,*grid.shape[-2:],device=grid.device,dtype=torch.float16 if self.model.amp else torch.float32);self.age=torch.zeros(n,device=grid.device)
            refresh=torch.ones(n,device=grid.device,dtype=torch.bool)
        else:
            self.age+=1;changed=(terrain!=self.snapshot).any(1);count=changed.sum((1,2));stairs=(terrain[:,2]!=self.snapshot[:,2]).any((1,2))
            refresh=(count>0)&((self.age>=self.interval)|(count>=self.threshold)|stairs)
        ids=refresh.nonzero().flatten();number=len(ids)
        if number:
            # Bucket variable refresh batches to avoid excessive convolution tuning.
            bucket=min(n,max(16,1<<(number-1).bit_length()));self.total_encoded_slots+=bucket;padded=ids[torch.arange(bucket,device=grid.device)%number]
            with torch.autocast(grid.device.type,dtype=torch.float16,enabled=self.model.amp and grid.is_cuda):encoded=self.model.encoder(terrain[padded])
            self.features[ids]=encoded[:number].to(self.features.dtype);self.snapshot[ids]=terrain[ids];self.age[ids]=0
        changed=(terrain!=self.snapshot).flatten(1).any(1);age=self.age*changed
        self.refreshes+=number;self.observations+=n;self.total_refreshes+=number;self.total_observations+=n
        return self.model.inputs(grid,stats,self.features,age)
    @torch.no_grad()
    def __call__(self,grid,mask,stats,intervene=None):
        local,features,scalars=self.prepare(grid,stats)
        if intervene=='erase_global':features=torch.zeros_like(features)
        with torch.autocast(grid.device.type,dtype=torch.float16,enabled=self.model.amp and grid.is_cuda):return self.model.actor(local,features,scalars,mask)[0]
