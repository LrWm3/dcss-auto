"""Position-aware readers of cached terrain, and a count-only global baseline."""
import torch
from torch import nn
from torch.nn import functional as F
from cached_policy import MapEncoder

def crop(x,pos,offsets):
    h,w=x.shape[-2:];xy=pos[:,None,None,:].long()+offsets.long()
    valid=(xy[...,0]>=0)&(xy[...,0]<w)&(xy[...,1]>=0)&(xy[...,1]<h)
    ix=(xy[...,1].clamp(0,h-1)*w+xy[...,0].clamp(0,w-1)).flatten(1)
    out=x.flatten(2).gather(2,ix[:,None].expand(-1,x.shape[1],-1))
    return out.reshape(len(x),x.shape[1],*offsets.shape[1:3])*valid[:,None]

def count_map(terrain,block=4,boundary=False,visits=False):
    """Block counts / block area. Frontier = known floor with an unknown 8-neighbor.

    Uses only observed floor/wall/stairs and optionally actual visited history. Outside-array padding is not an
    unknown neighbor, and padded block cells contribute zero to all counts.
    """
    floor=terrain[:,0:1]>0;wall=terrain[:,1:2]>0;seen=floor|wall
    frontier=floor&(F.max_pool2d((~seen).float(),3,1,1)>0)
    channels=torch.cat([seen,frontier,floor,wall,terrain[:,2:3]>0],1).float()
    if visits:channels=torch.cat([channels,(terrain[:,3:4]>0).float()],1)
    h,w=terrain.shape[-2:];counts=F.avg_pool2d(F.pad(channels,(0,(-w)%block,0,(-h)%block)),block)
    return torch.cat([counts,boundary_map(floor,block)],1) if boundary else counts

def boundary_map(floor,block=4):
    """Known-floor legal crossing counts to each of eight neighboring blocks.

    Cardinal neighbors admit up to 3*block-2 crossings (including diagonals
    crossing that edge); diagonal blocks admit one corner-to-corner crossing.
    Does not compute reachability between entrances inside a block.
    """
    n,_,h,w=floor.shape;gh=(h+block-1)//block;gw=(w+block-1)//block
    tiles=F.pad(floor,(0,(-w)%block,0,(-h)%block)).reshape(n,gh,block,gw,block).permute(0,1,3,2,4)
    def neighbor(x,dx,dy):
        out=torch.roll(x,shifts=(-dy,-dx),dims=(1,2))
        if dy<0:out[:,0]=False
        if dy>0:out[:,-1]=False
        if dx<0:out[:,:,0]=False
        if dx>0:out[:,:,-1]=False
        return out
    sides=[tiles[...,0,:],tiles[...,:,-1],tiles[...,-1,:],tiles[...,:,0]]
    directions=[(0,-1),(1,0),(0,1),(-1,0)];edges=[]
    for i,(dx,dy) in enumerate(directions):
        src=sides[i];dst=neighbor(sides[(i+2)%4],dx,dy)
        total=(src&dst).sum(-1)+(src[...,1:]&dst[...,:-1]).sum(-1)+(src[...,:-1]&dst[...,1:]).sum(-1)
        edges.append(total.float()/(3*block-2))
    for dx,dy in [(1,-1),(1,1),(-1,1),(-1,-1)]:
        sy=0 if dy<0 else -1;sx=0 if dx<0 else -1;ty=-1 if dy<0 else 0;tx=-1 if dx<0 else 0
        edges.append((tiles[...,sy,sx]&neighbor(tiles[...,ty,tx],dx,dy)).float())
    return torch.stack(edges,1)

class CompactPolicy(nn.Module):
    def __init__(self,kind='attn',amp=False):
        super().__init__();self.kind=kind;self.amp=amp;self.block=2 if kind in ('counts2','counts2_visits','counts2_visit_bits') else 4;self.visits=kind in ('counts_visits','counts2_visits','counts2_visit_bits')
        self.local=nn.Sequential(nn.Conv2d(11,16,3,padding=1),nn.ReLU(),nn.Conv2d(16,16,3,padding=1),nn.ReLU(),nn.Flatten(),nn.Linear(16*15*15,64),nn.ReLU())
        for name,r in [('local_xy',7),('read_xy',1)]:
            yy,xx=torch.meshgrid(torch.arange(-r,r+1),torch.arange(-r,r+1),indexing='ij');self.register_buffer(name,torch.stack([xx,yy],-1)[None],persistent=False)
        if kind=='attn':
            self.encoder=MapEncoder();self.patch=nn.Sequential(nn.Linear(144,64),nn.ReLU())
            self.query=nn.Linear(132,64);self.keys=nn.Linear(18,64);self.values=nn.Linear(18,64)
            self.readers=nn.ModuleList([nn.MultiheadAttention(64,4,batch_first=True) for _ in range(2)])
            self.norms=nn.ModuleList([nn.LayerNorm(64) for _ in range(2)])
            width=194
        else:
            self.encoder=nn.Sequential(nn.Conv2d(48,24,1),nn.ReLU()) if kind=='coarse' else nn.Identity()
            channels=24 if kind=='coarse' else 13 if kind=='count_edges' else 9 if kind=='counts2_visit_bits' else 6 if self.visits else 5
            self.dynamic=nn.Sequential(nn.Conv2d(channels+3,32,3,padding=1),nn.ReLU(),nn.Conv2d(32,32,3,padding=2,dilation=2),nn.ReLU(),nn.Conv2d(32,32,3,padding=4,dilation=4),nn.ReLU())
            self.readout=nn.Sequential(nn.Linear(32*25,128),nn.ReLU());width=196
        self.shared=nn.Sequential(nn.Linear(width,128),nn.ReLU());self.policy=nn.Linear(128,19);self.value=nn.Linear(128,1)
        nn.init.zeros_(self.value.weight);nn.init.zeros_(self.value.bias)
    def terrain(self,grid):return grid[:,[0,1,4,2] if self.visits else [0,1,4]].contiguous()
    def encode_map(self,terrain):
        if self.kind=='attn':return self.encoder(terrain)
        if self.kind=='counts2_visit_bits':
            h,w=terrain.shape[-2:]
            bits=F.pixel_unshuffle(F.pad((terrain[:,3:4]>0).float(),(0,(-w)%2,0,(-h)%2)),2)
            return torch.cat([count_map(terrain[:,:3],2),bits],1)
        if self.kind in ('counts','counts2','count_edges','counts_visits','counts2_visits'):return count_map(terrain,self.block,self.kind=='count_edges',self.visits)
        h,w=terrain.shape[-2:];packed=F.pixel_unshuffle(F.pad(terrain.float()/255.,(0,(-w)%4,0,(-h)%4)),4)
        return self.encoder(packed)
    def read_map(self,grid,mask,stats,memory,intervene=None,critic=False):
        h,w=grid.shape[-2:];pos=stats[:,2:4];lo=crop(grid,pos,self.local_xy).float()/255.
        lo=torch.cat([lo[:,:6],lo[:,6:]*lo[:,3:4]],1);lo=self.local(lo)
        if self.kind=='attn':
            patch=self.patch(crop(memory,pos,self.read_xy).flatten(1).float())
            pooled=F.avg_pool2d(memory,4,ceil_mode=True);gh,gw=pooled.shape[-2:]
        else:pooled=memory;gh,gw=memory.shape[-2:]
        yy,xx=torch.meshgrid(torch.arange(gh,device=grid.device),torch.arange(gw,device=grid.device),indexing='ij')
        centers=torch.stack([xx*self.block+(self.block-1)/2,yy*self.block+(self.block-1)/2]).float()[None];relative=(centers-pos[:,:,None,None])/stats.new_tensor([w,h])[None,:,None,None]
        if self.kind=='attn':
            tokens=torch.cat([pooled.float(),relative],1).flatten(2).transpose(1,2)
            k=self.keys(tokens);v=self.values(tokens);q=self.query(torch.cat([lo,patch,stats[:,:2],pos/stats.new_tensor([w,h])],1))[:,None]
            for reader,norm in zip(self.readers,self.norms):q=norm(q+reader(q,k,v,need_weights=False)[0])
            gl=torch.cat([patch,q[:,0]],1)
            if intervene=='erase_global':gl=torch.zeros_like(gl)
            z=torch.cat([lo,gl,stats[:,:2]],1)
        else:
            player=((xx[None]==(pos[:,0]/self.block).long()[:,None,None])&(yy[None]==(pos[:,1]/self.block).long()[:,None,None])).float()[:,None]
            mixed=self.dynamic(torch.cat([memory.float(),relative,player],1))
            near=crop(mixed,(pos/self.block).floor(),self.read_xy).flatten(1);whole=F.adaptive_avg_pool2d(mixed,(4,4)).flatten(1)
            gl=self.readout(torch.cat([near,whole],1))
            if intervene=='erase_global':gl=torch.zeros_like(gl)
            z=torch.cat([lo,gl,stats[:,:2],(pos%self.block)/(self.block-1)],1)
        hidden=self.shared(z);logits=self.policy(hidden).float().masked_fill(mask==0,-1e9)
        return (logits,self.value(hidden).float().squeeze(-1)) if critic else logits
    def forward(self,grid,mask,stats,intervene=None):
        with torch.autocast(grid.device.type,dtype=torch.float16,enabled=self.amp and grid.is_cuda):
            return self.read_map(grid,mask,stats,self.encode_map(self.terrain(grid)),intervene)

class ExactCache:
    """Refresh each changed map input (including visits when enabled). Invalidate after updates.

    For supervised training call the model directly, retaining encoder gradients.
    This wrapper is inference-only and must be reset after model or world resets.
    """
    def __init__(self,model):self.model=model;self.reset_cache()
    def reset_cache(self):self.snapshot=None;self.memory=None;self.refreshes=0;self.slots=0
    @torch.no_grad()
    def __call__(self,grid,mask,stats,intervene=None):
        terrain=self.model.terrain(grid)
        with torch.autocast(grid.device.type,dtype=torch.float16,enabled=self.model.amp and grid.is_cuda):
            if self.snapshot is None:
                self.memory=self.model.encode_map(terrain);self.snapshot=terrain.clone();self.refreshes+=len(grid)
            else:
                ids=(terrain!=self.snapshot).flatten(1).any(1).nonzero().flatten()
                if len(ids):
                    n=len(ids);bucket=min(len(grid),max(16,1<<(n-1).bit_length()));padded=ids[torch.arange(bucket,device=grid.device)%n]
                    self.memory[ids]=self.model.encode_map(terrain[padded])[:n].to(self.memory.dtype);self.snapshot[ids]=terrain[ids];self.refreshes+=n
            self.slots+=len(grid)
            return self.model.read_map(grid,mask,stats,self.memory,intervene)
