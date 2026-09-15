"""Sleep task with doubled first-seen reward and a local seen-history channel."""
import learn_env_sleep

learn_env_sleep._LIB = None
learn_env_sleep.LIB_NAME = 'learn_sleep_explore_seen.so'
Env = learn_env_sleep.Env
