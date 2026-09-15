"""History order, episode isolation, and checkpoint raw-observation restore."""
import torch
from frame_stack import FrameStack


class FakeEnv:
    def __init__(self):
        self.obs = torch.tensor([[1., 2.], [3., 4.]])

    def reset(self, seed):
        self.obs.fill_(seed)

    def step(self, actions):
        self.obs.copy_(torch.tensor([[5., 6.], [7., 8.]]))
        out = torch.zeros(2, 8)
        out[1, 1] = 1  # Row one has auto-reset into its next episode.
        return self.obs, out


env = FrameStack(FakeEnv())
env.step(None)
assert torch.equal(env.obs[0], torch.tensor([1., 2., 1., 2., 1., 2., 5., 6.]))
assert torch.equal(env.obs[1], torch.tensor([7., 8., 7., 8., 7., 8., 7., 8.]))
env.base.obs.zero_()
env.restore_raw_observation()
assert torch.equal(env.base.obs, torch.tensor([[5., 6.], [7., 8.]]))
env.reset(9)
assert (env.obs == 9).all()
print('PASS: frame ordering, episode isolation, reset, and raw observation restore')
