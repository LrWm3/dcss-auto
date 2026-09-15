"""Sleep task with doubled novelty reward and a 12x12 frontier ring."""
import learn_env_sleep

learn_env_sleep._LIB = None
learn_env_sleep.LIB_NAME = 'learn_sleep_explore_ring12.so'
Env = learn_env_sleep.Env
