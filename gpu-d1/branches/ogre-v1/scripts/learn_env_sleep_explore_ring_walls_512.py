"""Corrected ring environment with a 512-decision episode deadline."""
from learn_env_sleep_explore_ring_walls import Env as _BaseEnv


class Env(_BaseEnv):
    def __init__(self, batch=512, enemies=6, seed=0, device='cuda', limit=512):
        super().__init__(batch=batch, enemies=enemies, seed=seed, device=device, limit=512)
