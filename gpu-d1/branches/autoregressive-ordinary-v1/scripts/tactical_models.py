"""Type-first autoregressive policy with one shared conditional direction head."""
import math
import torch
from torch import nn
from torch.distributions import Categorical
from symmetry import D4

class ActionDistribution:
    def __init__(self,types,directions,mask):
        valid=mask[:,:16].reshape(-1,2,8).bool()
        type_mask=torch.cat((valid.any(-1),mask[:,16:].bool()),-1)
        self.types=Categorical(logits=types.masked_fill(~type_mask,-1e9))
        # A safe dummy conditional for unavailable types; their joint mass is zero.
        safe=valid | ~valid.any(-1,keepdim=True)
        self.directions=Categorical(logits=directions.masked_fill(~safe,-1e9))
        self.probs=torch.cat(((self.types.probs[:,:2,None]*self.directions.probs).flatten(1),self.types.probs[:,2:]),-1)
    def sample(self):
        kind=self.types.sample();direction=self.directions.sample()
        selected=direction.gather(1,kind.clamp_max(1)[:,None]).squeeze(1)
        return torch.where(kind<2,8*kind+selected,kind+14)
    def greedy(self):
        kind=self.types.probs.argmax(-1)
        direction=self.directions.probs.argmax(-1).gather(1,kind.clamp_max(1)[:,None]).squeeze(1)
        return torch.where(kind<2,8*kind+direction,kind+14)
    def log_prob(self,action):
        kind=torch.where(action<8,0,torch.where(action<16,1,action-14))
        conditional=self.directions.logits.gather(2,(action%8)[:,None,None].expand(-1,2,1)).squeeze(-1).gather(1,kind.clamp_max(1)[:,None]).squeeze(1)
        return self.types.log_prob(kind)+torch.where(kind<2,conditional,0.)
    def entropy(self):
        return self.types.entropy()+(self.types.probs[:,:2]*self.directions.entropy()).sum(-1)

class Policy(nn.Module):
    def __init__(self,architecture='d4_exact',width=128):
        super().__init__();self.architecture=architecture;self.d4=None
        self.body=nn.Sequential(nn.Linear(958,width),nn.Tanh(),nn.Linear(width,width),nn.Tanh())
        self.actor=nn.Linear(width,4);self.critic=nn.Linear(width,1)
        self.type_embedding=nn.Embedding(2,16)
        self.direction=nn.Sequential(nn.Linear(width+16,64),nn.Tanh(),nn.Linear(64,8))
        for layer in self.modules():
            if isinstance(layer,nn.Linear):nn.init.orthogonal_(layer.weight,math.sqrt(2));nn.init.zeros_(layer.bias)
        nn.init.normal_(self.type_embedding.weight,std=.1)
        nn.init.orthogonal_(self.actor.weight,.01);nn.init.orthogonal_(self.direction[-1].weight,.01);nn.init.orthogonal_(self.critic.weight,1)
        first=self.body[0];first.weight=nn.Parameter(torch.cat((first.weight.detach(),torch.zeros(width,41)),1));first.in_features+=41
    def raw(self,obs):
        h=self.body(obs);n=len(h)
        embedding=self.type_embedding.weight[None].expand(n,-1,-1)
        directions=self.direction(torch.cat((h[:,None].expand(-1,2,-1),embedding),-1))
        return self.actor(h),directions,self.critic(h).squeeze(-1)
    def forward(self,obs,mask,temperature=None):
        if self.architecture=='d4_exact':
            if self.d4 is None:self.d4=D4(obs.device)
            n=len(obs);groups=torch.arange(8,device=obs.device).repeat_interleave(n)
            types,directions,value=self.raw(self.d4.observation(obs.repeat(8,1),groups))
            types=types.reshape(8,n,4).mean(0)
            directions=directions.reshape(8,n,2,8).gather(-1,self.d4.forward[:,:8][:,None,None,:].expand(-1,n,2,-1)).mean(0)
            value=value.reshape(8,n).mean(0)
        else:types,directions,value=self.raw(obs)
        if temperature is not None:
            types=types/temperature[:,None]
            directions=directions/temperature[:,None,None]
        return ActionDistribution(types,directions,mask),value

class ActorOnly(nn.Module):
    def __init__(self,model):super().__init__();self.model=model
    def forward(self,obs,mask,temperature=None):return self.model(obs,mask)[0]
