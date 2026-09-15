"""Full spatial map PPO ablation, retaining original local combat inputs."""
import math
import torch
from torch import nn
from torch.distributions import Categorical
import train_clear
from learn_env import ROOT
from learn_env_sleep_spatial import Env

class Policy(nn.Module):
    def __init__(self, obs=22606):
        super().__init__()
        assert obs == 206+4*70*80
        # Non-overlapping first patches retain all cells as learnable inputs.
        self.spatial = nn.Sequential(nn.Conv2d(4, 8, 4, stride=4), nn.ReLU(),
                                     nn.Conv2d(8, 16, 3, stride=2, padding=1), nn.ReLU(), nn.Flatten())
        self.body = nn.Sequential(nn.Linear(16*9*10+206,128), nn.Tanh(), nn.Linear(128,128),nn.Tanh())
        self.actor=nn.Linear(128,9); self.critic=nn.Linear(128,1)
        for layer in self.modules():
            if isinstance(layer,(nn.Linear,nn.Conv2d)):
                nn.init.orthogonal_(layer.weight,math.sqrt(2)); nn.init.zeros_(layer.bias)
        nn.init.orthogonal_(self.actor.weight,0.01); nn.init.orthogonal_(self.critic.weight,1)
    def forward(self,obs,mask):
        maps=obs[:,206:].reshape(-1,4,70,80)
        maps=torch.nn.functional.pad(maps,(0,0,0,2))
        h=self.body(torch.cat((obs[:,:206],self.spatial(maps)),dim=1))
        return Categorical(logits=self.actor(h).masked_fill(mask==0,-1e9)),self.critic(h).squeeze(-1)

train_clear.Env=Env
train_clear.Policy=Policy
train_clear.ENV_SCOPE='fixed map; sleep radius 6; doubled exploration reward; four full spatial map channels plus original local inputs'
train_clear.EXTRA_SOURCES=[ROOT/'scripts/learn_env_sleep.py',ROOT/'scripts/learn_env_sleep_spatial.py',ROOT/'scripts/train_sleep_spatial.py']
train_clear.META_EXTRA=dict(observation_size=22606,map_channels=['floor','seen_floor','player','enemy_hp_div16'],exploration_reward=0.002,sleep_radius=6,build_define=['SLEEP_ON','EXPLORE_REWARD','SPATIAL_MAP_OBS'])
if __name__=='__main__': train_clear.main()
