"""Full visible map recentered on the player, with exact D4 averaging."""
import math
import torch
from torch import nn
from torch.distributions import Categorical
from symmetry import D4

class Policy(nn.Module):
    def __init__(self,architecture='centered_map',width=128):
        super().__init__();self.architecture=architecture;self.d4=None;self.fast_maps=False
        self.spatial=nn.Sequential(nn.Conv2d(3,8,4,stride=4),nn.ReLU(),nn.Conv2d(8,16,3,stride=2,padding=1),nn.ReLU(),nn.Conv2d(16,16,3,stride=2,padding=1),nn.ReLU(),nn.Flatten())
        self.body=nn.Sequential(nn.Linear(1600+999,width),nn.Tanh(),nn.Linear(width,width),nn.Tanh())
        self.actor=nn.Linear(width,10);self.critic=nn.Linear(width,1)
        for layer in self.modules():
            if isinstance(layer,(nn.Linear,nn.Conv2d)):nn.init.orthogonal_(layer.weight,math.sqrt(2));nn.init.zeros_(layer.bias)
        nn.init.orthogonal_(self.actor.weight,.01);nn.init.orthogonal_(self.critic.weight,1)
        self.register_buffer('delta',torch.arange(-79,80),persistent=False)

    def centered(self,obs):
        # 159 square covers any displacement on an 80x70 map, and all rotations.
        px=(obs[:,652]*80).round().long();py=(obs[:,653]*70).round().long()
        x=px[:,None,None]+self.delta[None,None,:];y=py[:,None,None]+self.delta[None,:,None]
        valid=(x>=0)&(x<80)&(y>=0)&(y<70)
        indices=(y.clamp(0,69)*80+x.clamp(0,79)).flatten(1)
        terrain=obs[:,999:].gather(1,indices).reshape(-1,159,159)*valid
        hp=torch.zeros_like(terrain)
        sleep=torch.zeros_like(terrain)
        records=obs[:,450:650].reshape(-1,40,5)
        dx=(records[:,:,0]*80).round().long();dy=(records[:,:,1]*70).round().long()
        slots=((dy+79)*159+dx+79).clamp(0,159*159-1)
        hp.flatten(1).scatter_add_(1,slots,records[:,:,2]*records[:,:,4])
        sleep.flatten(1).scatter_add_(1,slots,obs[:,959:999]*records[:,:,4])
        return torch.stack((terrain,hp,sleep),1)

    def forward(self,obs,mask):
        if self.d4 is None:self.d4=D4(obs.device)
        if self.fast_maps:
            from fast_maps import spatial
            dtype=torch.float16 if torch.is_autocast_enabled() else torch.float32
            return self.finish(obs[:,:999],spatial(obs,dtype),mask)
        return self.aggregate(obs[:,:999],self.centered(obs),mask)

    def aggregate(self,local,maps,mask):
        if self.d4 is None:self.d4=D4(local.device)
        variants=[]
        for g in range(8):
            m=maps.flip(-1) if g//4 else maps
            variants.append(torch.rot90(m,-(g%4),(-2,-1)))
        spatial=torch.cat(variants)
        spatial=nn.functional.pad(spatial,(0,1,0,1))
        return self.finish(local,spatial,mask)

    def finish(self,local,spatial,mask):
        n=local.shape[0]
        groups=torch.arange(8,device=local.device).repeat_interleave(n)
        local=self.d4.observation(local.repeat(8,1),groups)
        local[:,652:654]=0
        encoded=self.spatial(spatial)
        h=self.body(torch.cat((local,encoded),1))
        logits=self.actor(h).gather(1,self.d4.forward[groups]).reshape(8,n,10).mean(0)
        value=self.critic(h).reshape(8,n).mean(0)
        return Categorical(logits=logits.float().masked_fill(mask==0,-1e9)),value.float()
