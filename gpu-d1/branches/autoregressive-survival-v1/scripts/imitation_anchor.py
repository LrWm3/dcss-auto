"""Fixed-reference feature or policy protection; no validation observations used."""
import copy
import torch
from symmetry import D4

class ImitationAnchor:
    def __init__(self, model, job):
        self.kind = job['anchor_kind']
        self.scope = job.get('anchor_scope')
        self.weight = job['anchor_weight']
        self.reference = copy.deepcopy(model).eval().requires_grad_(False)
        data = torch.load(job['anchor_buffer'], map_location='cuda', weights_only=False)
        self.obs, self.mask = data['obs'], data['mask']
        self.d4 = D4(self.obs.device)
        self.size = job.get('anchor_batch', 512)

    def loss(self, model, obs, mask):
        n = min(self.size // 2, len(obs))
        # Sampling uses the checkpointed Torch RNG, so resuming is reproducible.
        replay = torch.randint(len(self.obs), (n,), device=obs.device)
        current = torch.randint(len(obs), (n,), device=obs.device)
        x = torch.cat((obs[current], self.obs[replay]))
        m = torch.cat((mask[current], self.mask[replay]))
        if self.kind == 'feature':
            # Cover the inputs actually processed by the exact-D4 encoder.
            x = self.d4.observation(x, torch.randint(8, (len(x),), device=x.device))
            with torch.no_grad(): target = self.reference.body[:2](x)
            return self.weight * (model.body[:2](x) - target).square().mean()
        if self.kind == 'policy':
            with torch.no_grad(): target = self.reference(x, m)[0].probs
            actual = model(x, m)[0].probs
            # Exact joint KL includes both the type and conditional direction.
            kl=(target * (target.clamp_min(1e-30).log() - actual.clamp_min(1e-30).log())).sum(-1)
            if self.scope == 'no_visible_awake_enemy':
                eligible=(x[:,959:999]>=0).all(-1).float()
                return self.weight*(eligible*kl).sum()/eligible.sum().clamp_min(1)
            return self.weight*kl.mean()
        raise ValueError(self.kind)
