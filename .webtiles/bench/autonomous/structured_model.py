"""Spatial encoder and masked item-set encoder for semantic action scoring."""
import torch
from torch import nn
import structured_features as f


class StructuredScorer(nn.Module):
    def __init__(self, hidden):
        super().__init__()
        self.spatial = nn.Sequential(nn.Conv2d(f.GRID_CHANNELS,32,3,padding=1),nn.ReLU(),
            nn.Conv2d(32,32,3,padding=1),nn.ReLU(),nn.AdaptiveAvgPool2d((3,3)),nn.Flatten())
        self.items = nn.Sequential(nn.Linear(f.ITEM_DIM,64),nn.ReLU())
        self.globals = nn.Sequential(nn.Linear(f.GLOBAL_DIM,128),nn.ReLU())
        self.head = nn.Sequential(nn.Linear(288+128+128+f.ACTION_DIM,hidden),
            nn.LayerNorm(hidden),nn.ReLU(),nn.Linear(hidden,hidden),nn.ReLU(),nn.Linear(hidden,1))

    def forward(self, x):
        if isinstance(x, tuple):
            state, actions = x
            shared = True
        else:
            state, actions = x[:,:f.STATE_DIM], x[:,f.STATE_DIM:]
            shared = torch.equal(state, state[:1].expand_as(state))
        # tensor_for_actions gives one observation and its legal actions.
        # Encode shared geometry once. Mixed-state tensors remain supported.
        if shared:
            state = state[:1]
        context = self.encode_context(state)
        if shared:
            context = context.expand(actions.shape[0],-1)
        return self.head(torch.cat((context,actions),dim=1))

    def encode_context(self, state):
        """Encode each observation once, also for ragged PPO minibatches."""
        global_ = self.globals(state[:,:f.GLOBAL_DIM])
        grid = state[:,f.GLOBAL_DIM:f.GLOBAL_DIM+f.GRID_DIM]
        grid = grid.reshape(-1,f.SIDE,f.SIDE,f.GRID_CHANNELS).permute(0,3,1,2)
        inventory = state[:,f.GLOBAL_DIM+f.GRID_DIM:].reshape(-1,f.INVENTORY_SLOTS,f.ITEM_DIM)
        mask = inventory[:,:,:1]
        entities = self.items(inventory)*mask
        mean = entities.sum(1)/mask.sum(1).clamp_min(1)
        maximum = entities.max(1).values
        return torch.cat((self.spatial(grid),global_,mean,maximum),dim=1)

    def packed(self, states, actions, owners):
        context = self.encode_context(states)
        return self.head(torch.cat((context[owners],actions),dim=1)).squeeze(-1)
