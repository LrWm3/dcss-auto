"""Sleep task with a once-per-episode reward for newly seen floor cells."""
import learn_env_sleep

learn_env_sleep._LIB = None
learn_env_sleep.LIB_NAME = 'learn_sleep_explore.so'
Env = learn_env_sleep.Env
