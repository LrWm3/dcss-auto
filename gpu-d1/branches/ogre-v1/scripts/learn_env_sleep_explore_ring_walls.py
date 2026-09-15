"""Sleep + doubled exploration reward environment with known wall marks."""
import learn_env_sleep

learn_env_sleep._LIB = None
learn_env_sleep.LIB_NAME = 'learn_sleep_explore_ring_walls.so'
Env = learn_env_sleep.Env
