"""Sleep task with the fixed terrain map appended to every observation."""
import learn_env_sleep

# Reuse the exact sleep environment wrapper and ABI. The alternate binary has
# the same state and transition rules, but reports 206 + 5,600 observations.
learn_env_sleep._LIB = None
learn_env_sleep.LIB_NAME = 'learn_sleep_map.so'
Env = learn_env_sleep.Env
