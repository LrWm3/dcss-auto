import pathlib
import torch
from tactical_models import Policy
from learn_env_ring_multi import Env

ROOT=pathlib.Path(__file__).resolve().parents[3]
SUITE=ROOT/'learning-runs/d1-stairs'
CORPUS=ROOT/'fixtures/d1-corpus-388'
SOURCE=ROOT/'learning-runs/autoregressive-ordinary/runs/wait-seed0/latest.pt'
REFERENCE=ROOT/'learning-runs/autoregressive-imitation/imitation.pt'
BUFFER=ROOT/'learning-runs/autoregressive-anchor-buffer.pt'

def expand_weights(weights):
    model=Policy('d4_exact',128)
    new=model.state_dict()
    for k,v in weights.items():
        if k=='body.0.weight':
            new[k].zero_();new[k][:,:999]=v
        elif k=='actor.weight':
            new[k].zero_();new[k][:4]=v
        elif k=='actor.bias':
            new[k][:4]=v;new[k][4]=-4.
        else:new[k].copy_(v)
    model.load_state_dict(new)
    return model.cuda()

def env(split='train',batch=512,seed=0):
    return Env(batch,24,seed=seed,corpus=CORPUS/split,
               map_limit={'train':256,'validation':32,'test':100}[split],
               map_filter=-1 if split=='train' else -2,
               library_path=ROOT/'learning-runs/d1-stairs-assets'/f'stairs-clump{int(split=="train")}.so')

def pad(obs,mask):
    return torch.nn.functional.pad(obs,(0,16)),torch.nn.functional.pad(mask,(0,1))

def weights(model):
    return {k:v.detach().cpu().clone() for k,v in model.state_dict().items()}

class NavigationAnchor:
    """Existing imitation KL, restricted to pre-discovery non-combat states."""
    def __init__(self):
        self.reference=expand_weights(torch.load(REFERENCE,map_location='cpu',weights_only=False)['model']).eval().requires_grad_(False)
        b=torch.load(BUFFER,map_location='cuda',weights_only=False)
        self.obs,self.mask=pad(b['obs'],b['mask'])
    def loss(self,model,obs,mask):
        n=min(256,len(obs))
        ix=torch.randint(len(obs),(n,),device='cuda');ib=torch.randint(len(self.obs),(n,),device='cuda')
        x=torch.cat((obs[ix],self.obs[ib]));m=torch.cat((mask[ix],self.mask[ib]))
        with torch.no_grad():target=self.reference(x,m)[0].probs
        actual=model(x,m)[0].probs
        kl=(target*(target.clamp_min(1e-30).log()-actual.clamp_min(1e-30).log())).sum(-1)
        eligible=(x[:,959:999]>=0).all(-1)&(x[:,999]==0)
        return (kl*eligible).sum()/eligible.sum().clamp_min(1)
