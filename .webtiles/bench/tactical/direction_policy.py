"""Shared action scorer using player-known directional geometry, not label inputs."""
import numpy as np
import torch
from torch import nn
from action_env import ACTIONS
from experiment import DIRECTIONS
from goal_controllers import geometry, paths, dist
from rich_features import values

WIDTH = 32


def directional_features(state, mask):
    cells=geometry(state); enemies=values(state.get('monsters'));routes=paths(state,ignore_occupied=True)
    p=state.get('player',{})
    global_features=[state['hp']/state['max_hp'], min(state['max_hp']/200,2),
        min(len(enemies)/8,2), float(state.get('safe',False)), float(state.get('unseen',False)),
        float(state.get('confused',False)), float(state.get('berserk',False)),
        float(state.get('cooldown',False)), p.get('ac',0)/50,p.get('ev',0)/50,
        p.get('xl',0)/27, float(state.get('poisoned',False))]
    rows=[]
    for i,action in enumerate(ACTIONS):
        x,y=DIRECTIONS.get(action,(0,0));cell=cells.get((x,y),{})
        direct=[e for e in enemies if (e['x'],e['y'])==(x,y)]
        route_lengths=[len(routes[(e['x'],e['y'])]) for e in enemies
                       if routes.get((e['x'],e['y'])) and routes[(e['x'],e['y'])][0]==action]
        nearest=min([dist((e['x']-x,e['y']-y)) for e in enemies],default=16)
        align=max([(e['x']*x+e['y']*y)/max(1,dist((e['x'],e['y']))*2) for e in enemies],default=0)
        local=[float(mask[i]),x,y,float(action=='wait'),float(action=='berserk'),
            float(cell.get('traversable',False)),float(cell.get('unsafe',False)),float(bool(cell.get('cloud'))),
            float(cell.get('occupied',False)),float(cell.get('invisible_monster',False)),
            float(bool(direct)),max([e.get('threat',0)/3 for e in direct],default=0),
            min(nearest,16)/16,align,
            sum(dist((e['x']-x,e['y']-y))<=1 for e in enemies)/8,
            float(bool(route_lengths)),min(route_lengths,default=100)/100,
            sum(bool(cells.get((x+dx,y+dy),{}).get('traversable')) for dx,dy in DIRECTIONS.values())/8,
            max([e.get('threat',0)/3 for e in enemies],default=0),float(bool(enemies))]
        rows.append(global_features+local)
    result=np.asarray(rows,dtype=np.float32)
    if result.shape!=(10,WIDTH) or not np.isfinite(result).all():raise ValueError('Invalid direction features')
    return np.clip(result,-10,10)


def cap_probabilities(probabilities, factor=4):
    """Water-fill so no example gets more than factor times uniform probability."""
    p=np.asarray(probabilities,dtype=float)
    if len(p)==0 or factor<1 or np.any(p<=0) or not np.isfinite(p).all():
        raise ValueError('Positive finite probabilities and factor >= 1 required')
    cap=factor/len(p);out=np.zeros_like(p);free=np.ones(len(p),dtype=bool)
    while free.any():
        proposal=p[free]/p[free].sum()*(1-out.sum())
        high=proposal>cap+1e-15
        if not high.any():out[free]=proposal;break
        indices=np.flatnonzero(free)[high];out[indices]=cap;free[indices]=False
    return out


class DirectionPolicy(nn.Module):
    def __init__(self):
        super().__init__()
        self.scorer=nn.Sequential(nn.Linear(WIDTH,64),nn.Tanh(),nn.Linear(64,64),nn.Tanh(),nn.Linear(64,1))

    def forward(self, features, masks):
        return self.scorer(features).squeeze(-1).masked_fill(~masks,-1e9)

    def act(self,state,mask):
        with torch.no_grad():
            scores=self(torch.from_numpy(directional_features(state,mask)),torch.as_tensor(mask))
            return int(scores.argmax())
