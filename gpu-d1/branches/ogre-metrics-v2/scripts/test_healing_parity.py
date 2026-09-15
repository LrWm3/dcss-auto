"""Compare CPU/CUDA healing transitions including diagnostics and auto-resets."""
import pathlib
import sys
import torch
from learn_env_ring_multi import Env

lib=pathlib.Path(sys.argv[1])
kwargs=dict(batch=8, enemies=40, seed=123, map_limit=2, library_path=lib)
cpu=Env(device='cpu', **kwargs)
gpu=Env(device='cuda', **kwargs)
healed=deaths=0
for step in range(1100):
    assert torch.equal(cpu.obs, gpu.obs.cpu()), ('observation',step)
    assert torch.equal(cpu.mask, gpu.mask.cpu()), ('mask',step)
    action=torch.where(cpu.mask[:,9]>0,9,8).long()
    _,a=cpu.step(action)
    _,b=gpu.step(action.cuda())
    assert torch.equal(a,b.cpu()), ('transition',step)
    healed+=int((action==9).sum())
    deaths+=int(a[:,6].sum())
assert healed>0 and deaths>0, (healed,deaths)
print(f'PASS: 1100 CPU/CUDA steps, {healed} heals, {deaths} deaths; observations/masks/rewards/diagnostics identical')
