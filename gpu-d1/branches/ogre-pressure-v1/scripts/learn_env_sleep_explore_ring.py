"""Sleep task with doubled first-seen reward and an 11x11 frontier ring."""
import learn_env_sleep

learn_env_sleep._LIB = None
learn_env_sleep.LIB_NAME = 'learn_sleep_explore_ring.so'
Env = learn_env_sleep.Env
