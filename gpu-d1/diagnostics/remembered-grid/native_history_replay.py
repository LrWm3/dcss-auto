"""Bounded episode-backed DAgger replay with current-weight prefix reconstruction."""
import torch
from torch.nn import functional as F


class HistoryBuffer:
    def __init__(self, exact=False, balanced=False, capacity=1024, full=True):
        assert not exact, 'This comparison retains the original coarse model'
        self.capacity = capacity
        self.balanced = balanced
        self.full = full
        self.entries = []
        self.cursor = 0
        self.collected = torch.zeros(3, device='cuda', dtype=torch.long)
        self.sampled = torch.zeros_like(self.collected)
        self.prefix_frames = 0

    def add_episode_batch(self, values):
        # Each entry references immutable raw prepared observations, never learned
        # features or rollout hidden states. Eviction releases unreferenced waves.
        local, glob = values[:2]
        known = glob[:, :, 4].flatten(2).any(2)
        near = local[:, :, 4].flatten(2).any(2)
        group = torch.where(known, torch.where(near, 1, 2), 0)
        values = (*values, group)
        for start in range(0, values[0].shape[1], 16):
            valid = values[6][:, start:start + 16]
            ids = valid.any(1).nonzero().flatten().tolist()
            for k in range(3):
                self.collected[k] += ((group[:, start:start+16] == k) & valid).sum()
            for world in ids:
                entry = (values, world, start)
                if len(self.entries) < self.capacity:
                    self.entries.append(entry)
                else:
                    self.entries[self.cursor] = entry
                self.cursor = (self.cursor + 1) % self.capacity
        self._refresh_index()

    def _refresh_index(self):
        groups = []
        valid = []
        for values, world, start in self.entries:
            groups.append(values[7][world, start:start+16])
            valid.append(values[6][world, start:start+16])
        self.group = torch.stack(groups)
        self.valid = torch.stack(valid)
        self.available = [((self.group == k) & self.valid).any(1).nonzero().flatten() for k in range(3)]
        self.available = [a for a in self.available if len(a)]

    def coverage(self):
        return dict(collected=self.collected.tolist(),
                    retained=[int(((self.group == k) & self.valid).sum()) for k in range(3)],
                    sampled=self.sampled.tolist(), sequences=len(self.entries),
                    prefix_frames_encoded=self.prefix_frames)

    def sample(self, batch):
        if self.balanced:
            ix = torch.cat([a[torch.randint(len(a), ((batch+j)//len(self.available),), device='cuda')]
                            for j, a in enumerate(self.available)])
        else:
            ix = torch.randint(len(self.entries), (batch,), device='cuda')
        return [self.entries[i] for i in ix.tolist()]

    @torch.no_grad()
    def reconstruct(self, entries, model, execution):
        lengths = [start if self.full else min(start, 16) for _, _, start in entries]
        batch = len(entries)
        maximum = max(lengths)
        h = torch.zeros(batch, 128, device='cuda', dtype=torch.float16)
        if not maximum:
            return h
        # Encode only actual prefix frames. Bound CNN activations independently
        # of episode length; detach the whole prefix from backpropagation.
        inputs = [torch.cat([v[j][w, start-n:start] for (v,w,start),n in zip(entries,lengths)], 0)
                  for j in range(4)]
        total = sum(lengths)
        encoded = []
        with torch.autocast('cuda', dtype=torch.float16):
            for offset in range(0, total, 256):
                n = min(256, total-offset)
                chunk = [p[offset:offset+n] for p in inputs]
                if n < 256:
                    chunk = [torch.cat([p, p[-1:].expand(256-n, *p.shape[1:])]) for p in chunk]
                encoded.append(execution.encode(chunk)[:n])
            features = torch.cat(encoded)
            padded = features.new_zeros(batch, maximum, features.shape[-1])
            offset = 0
            for i,n in enumerate(lengths):
                padded[i,:n] = features[offset:offset+n]
                offset += n
            states, _ = model.sequence(padded)
            for i,n in enumerate(lengths):
                if n: h[i] = states[i,n-1]
        self.prefix_frames += total
        return h

    def logits(self, entries, model, execution):
        h = self.reconstruct(entries, model, execution)
        inputs = [torch.stack([v[j][w,start:start+16] for v,w,start in entries]) for j in range(4)]
        mask, target, valid, group = [torch.stack([v[j][w,start:start+16] for v,w,start in entries]) for j in range(4,8)]
        with torch.autocast('cuda', dtype=torch.float16):
            x = execution.encode([p.flatten(0,1) for p in inputs]).reshape(len(entries),16,-1)
            z, _ = model.sequence(x, h)
            logits = model.policy(z).float().masked_fill(mask == 0, -1e9)
        assert (mask.gather(-1,target[...,None]).squeeze(-1)[valid] > 0).all()
        return logits, target, valid, group

    def loss(self, model, execution, batch=16):
        logits, target, valid, groups = self.logits(self.sample(batch), model, execution)
        losses = F.cross_entropy(logits.flatten(0,1), target.flatten(), reduction='none').reshape(batch,16)
        counts = torch.stack([((groups == k) & valid).sum() for k in range(3)])
        self.sampled += counts
        if self.balanced:
            terms = torch.stack([(losses * ((groups == k) & valid)).sum()/counts[k].clamp_min(1) for k in range(3)])
            loss = terms.sum()/(counts > 0).sum()
        else:
            loss = (losses * valid).sum()/valid.sum()
        return loss, int(valid.sum())


@torch.no_grad()
def collect_history(env, buffer, model, policy, beta, seed, steps=512):
    env.reset(seed=seed)
    policy.reset_cache()
    history = []
    decisions = 0
    def snapshot():
        return (*[x.clone() for x in model.prepare(env.grid, env.stats)],
                env.mask.clone(), env.labels.clone(), env.active.clone())
    for tick in range(steps):
        history.append(snapshot())
        decisions += int(env.active.sum())
        action = env.labels.clone()
        assert (env.mask.gather(1, action[:,None]).squeeze() > 0).all()
        if beta < 1:
            predicted = policy(env.grid, env.mask, env.stats).argmax(-1)
            action = torch.where(torch.rand(env.batch, device='cuda') < beta, action, predicted)
        env.step(action, limit=1024)
        if not env.active.any():
            break
    if len(history) % 16:
        pad = list(snapshot())
        pad[-1] = torch.zeros_like(env.active)
        history.extend([tuple(pad)] * (16-len(history)%16))
    # Avoid the large multi-input CUDA stack path on channels-last tensors.
    buffer.add_episode_batch([torch.cat([torch.stack(x[i:i+16],1)
                                        for i in range(0,len(x),16)],1)
                              for x in zip(*history)])
    return decisions
