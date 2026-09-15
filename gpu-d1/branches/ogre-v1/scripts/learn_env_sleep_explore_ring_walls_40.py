"""Corrected 11x11 ring environment with 40 enemy slots and 1024 turns."""
import learn_env_sleep

learn_env_sleep._LIB = None
learn_env_sleep.LIB_NAME = 'learn_sleep_explore_ring_walls_40.so'


class Env(learn_env_sleep.Env):
    def __init__(self, batch=512, enemies=40, seed=0, device='cuda', limit=1024):
        super().__init__(batch=batch, enemies=enemies, seed=seed, device=device, limit=limit)
