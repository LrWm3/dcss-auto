"""Fixed observation history; duplicate initial frames and clear at auto-reset."""
import torch


class FrameStack:
    def __init__(self, base, frames=4):
        if frames < 2:
            raise ValueError('FrameStack requires at least two frames')
        self.base, self.frames = base, frames
        self.width = base.obs.shape[1]
        self.obs = base.obs.repeat(1, frames)

    def __getattr__(self, name):
        return getattr(self.base, name)

    def reset(self, seed):
        self.base.reset(seed)
        self.obs.copy_(self.base.obs.repeat(1, self.frames))
        return self.obs

    def step(self, actions, active=None):
        _, out = self.base.step(actions) if active is None else self.base.step(actions, active=active)
        self.obs[:, :-self.width].copy_(self.obs[:, self.width:].clone())
        self.obs[:, -self.width:].copy_(self.base.obs)
        ended = out[:, 1] > 0
        if active is not None:
            ended &= active
        self.obs[ended] = self.base.obs[ended].repeat(1, self.frames)
        return self.obs, out

    def restore_raw_observation(self):
        self.base.obs.copy_(self.obs[:, -self.width:])
