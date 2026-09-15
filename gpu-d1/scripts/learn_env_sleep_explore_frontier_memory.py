"""Sleep + doubled exploration reward environment with frontier memory features."""
import learn_env_sleep

learn_env_sleep._LIB = None
learn_env_sleep.LIB_NAME = 'learn_sleep_explore_frontier_memory.so'
Env = learn_env_sleep.Env
