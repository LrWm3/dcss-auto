"""Separate architecture screens: enemy-set pooling OR exact D4 group averaging."""
import math
import torch
from torch import nn
from torch.distributions import Categorical
from symmetry import D4

class Policy(nn.Module):
    def __init__(self, architecture='mlp', width=128):
        super().__init__();self.architecture=architecture
        if architecture=='enemy_set':
            self.enemy_encoder=nn.Sequential(nn.Linear(5,32),nn.Tanh(),nn.Linear(32,32),nn.Tanh())
            inputs=959-200+32
        else:inputs=958
        self.body=nn.Sequential(nn.Linear(inputs,width),nn.Tanh(),nn.Linear(width,width),nn.Tanh())
        self.actor=nn.Linear(width,10);self.critic=nn.Linear(width,1)
        for layer in self.modules():
            if isinstance(layer,nn.Linear):nn.init.orthogonal_(layer.weight,math.sqrt(2));nn.init.zeros_(layer.bias)
        nn.init.orthogonal_(self.actor.weight,.01);nn.init.orthogonal_(self.critic.weight,1)
        if architecture!='enemy_set':
            first=self.body[0];first.weight=nn.Parameter(torch.cat((first.weight.detach(),torch.zeros(width,1)),1));first.in_features+=1
        self.d4=None

    def raw(self,obs):
        if self.architecture=='enemy_set':
            enemies=obs[:,450:650].reshape(-1,40,5)
            pooled=(self.enemy_encoder(enemies)*(enemies[:,:,4:5]>0)).sum(1)/6.
            obs=torch.cat((obs[:,:450],obs[:,650:],pooled),1)
        h=self.body(obs);return self.actor(h),self.critic(h).squeeze(-1)

    def forward(self,obs,mask):
        if self.architecture=='d4_exact':
            if self.d4 is None:self.d4=D4(obs.device)
            n=obs.shape[0];groups=torch.arange(8,device=obs.device).repeat_interleave(n)
            transformed=self.d4.observation(obs.repeat(8,1),groups)
            logits,value=self.raw(transformed)
            # World action a corresponds to forward[g,a] in the transformed view.
            logits=logits.gather(1,self.d4.forward[groups]).reshape(8,n,10).mean(0)
            value=value.reshape(8,n).mean(0)
        else:logits,value=self.raw(obs)
        return Categorical(logits=logits.masked_fill(mask==0,-1e9)),value

class ActorOnly(nn.Module):
    def __init__(self,model):super().__init__();self.model=model
    def forward(self,obs,mask):return self.model(obs,mask)[0]
