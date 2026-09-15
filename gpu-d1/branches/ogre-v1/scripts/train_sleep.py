#!/usr/bin/env python3
"""Run the original PPO experiment with only the compile-time sleep rule enabled."""
import train_clear
from learn_env_sleep import Env
from learn_env import ROOT

train_clear.Env = Env
train_clear.ENV_SCOPE = 'one fixed native map; original task rules plus six-tile monster sleep'
train_clear.EXTRA_SOURCES = [ROOT / 'scripts/learn_env_sleep.py', ROOT / 'scripts/train_sleep.py']
train_clear.META_EXTRA = {'sleep_radius': 6, 'build_define': 'SLEEP_ON', 'sleep_only_ablation': True}


if __name__ == '__main__':
    train_clear.main()
