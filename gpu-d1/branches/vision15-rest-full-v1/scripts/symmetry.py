"""D4 camera augmentation, fixed per episode; no native simulator changes.

All positions use tile units before transforming. Absolute coordinates rotate
about the grid center (39.5,34.5), then retain the original /80,/70 scales.
This intentionally permits coordinates slightly outside [0,1] for quarter-turns
of the rectangular map. No clipping, hidden map extent input, or renormalization.
"""
import torch

DIRECTIONS = [(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1),(0,0)]

def xy(x, y, group):
    if group // 4:
        x = -x
    for _ in range(group % 4):
        x, y = -y, x
    return x, y

class D4:
    def __init__(self, device='cuda'):
        index = torch.arange(959).repeat(8,1)
        scale = torch.ones(8,959)
        offset = torch.zeros(8,959)
        forward = torch.arange(10).repeat(8,1)
        ring = ([(x,-8) for x in range(-8,9)] + [(x,8) for x in range(-8,9)] +
                [(-8,y) for y in range(-7,8)] + [(8,y) for y in range(-7,8)])
        for g in range(8):
            for start in [0,225,733]:
                for y in range(-7,8):
                    for x in range(-7,8):
                        xx,yy = xy(x,y,g)
                        index[g,start+(yy+7)*15+xx+7] = start+(y+7)*15+x+7
            for j,(x,y) in enumerate(ring):
                index[g,654+ring.index(xy(x,y,g))] = 654+j
            # Coordinate pairs: input normalization, optional absolute origin.
            pairs = [(j,80.,70.,0.,0.) for j in range(450,650,5)]
            pairs += [(719,80.,70.,0.,0.), (723,1.,1.,0.,0.), (652,80.,70.,39.5,34.5)]
            ex,ey = xy(1,0,g),xy(0,1,g)
            for j,sx,sy,cx,cy in pairs:
                units,center = [sx,sy],[cx,cy]
                for dst in range(2):
                    src = 0 if ex[dst] else 1
                    sign = ex[dst] if ex[dst] else ey[dst]
                    index[g,j+dst] = j+src
                    scale[g,j+dst] = sign*units[src]/units[dst]
                    offset[g,j+dst] = (center[dst]-sign*center[src])/units[dst]
            for a,(x,y) in enumerate(DIRECTIONS):
                forward[g,a] = DIRECTIONS.index(xy(x,y,g))
                if a<8:
                    index[g,725+int(forward[g,a])] = 725+a
        inverse = forward.argsort(1)
        self.index,self.scale,self.offset,self.forward,self.inverse = [a.to(device) for a in (index,scale,offset,forward,inverse)]

    def observation(self, obs, groups):
        return obs.gather(1,self.index[groups])*self.scale[groups]+self.offset[groups]

    def mask(self, mask, groups):
        return mask.gather(1,self.inverse[groups])

    def to_world(self, actions, groups):
        return self.inverse[groups].gather(1,actions[:,None]).squeeze(1)

class EpisodeSymmetry:
    def __init__(self, base, seed):
        self.base=base
        self.transform=D4(base.device)
        self.rng=torch.Generator(device=base.device).manual_seed(seed)
        self.groups=torch.randint(8,(base.batch,),generator=self.rng,device=base.device)
        self.refresh()

    def __getattr__(self,name):
        return getattr(self.base,name)

    def refresh(self):
        self.obs=self.transform.observation(self.base.obs,self.groups)
        self.mask=self.transform.mask(self.base.mask,self.groups)

    def reset(self,seed):
        self.base.reset(seed)
        self.groups=torch.randint(8,(self.base.batch,),generator=self.rng,device=self.base.device)
        self.refresh()
        return self.obs

    def step(self,actions,active=None):
        world_actions=self.transform.to_world(actions,self.groups)
        _,out=self.base.step(world_actions,active=active)
        ended=out[:,1]>0
        if active is not None:ended &= active
        # Fixed-size RNG draw avoids device synchronization for reset counts.
        fresh=torch.randint(8,(self.base.batch,),generator=self.rng,device=self.base.device)
        self.groups=torch.where(ended,fresh,self.groups)
        self.refresh()
        return self.obs,out

    def snapshot(self):
        return dict(groups=self.groups.cpu(),rng=self.rng.get_state(),raw_obs=self.base.obs.cpu(),raw_mask=self.base.mask.cpu())

    def restore(self,state):
        self.groups=state['groups'].to(self.base.device)
        self.rng.set_state(state['rng'])
        self.base.obs.copy_(state['raw_obs']);self.base.mask.copy_(state['raw_mask'])
        self.refresh()
