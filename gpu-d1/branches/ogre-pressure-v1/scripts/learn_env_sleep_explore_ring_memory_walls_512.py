"""Corrected ring-plus-frontier environment with a 512-decision deadline."""
import learn_env_sleep

learn_env_sleep._LIB = None
learn_env_sleep.LIB_NAME = 'learn_sleep_explore_ring_memory_walls.so'


class Env(learn_env_sleep.Env):
    def __init__(self, batch=512, enemies=6, seed=0, device='cuda', limit=512):
        super().__init__(batch=batch, enemies=enemies, seed=seed, device=device, limit=512)
