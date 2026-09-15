#!/usr/bin/env python3
"""PPO sleep task with the full static terrain map in the observation."""
import train_clear
from learn_env_sleep_map import Env
from learn_env import ROOT

train_clear.Env = Env
train_clear.ENV_SCOPE = 'one fixed native map; six-tile monster sleep; full static terrain observation'
train_clear.EXTRA_SOURCES = [
    ROOT / 'scripts/learn_env_sleep.py',
    ROOT / 'scripts/learn_env_sleep_map.py',
    ROOT / 'scripts/train_sleep_map.py',
]
train_clear.META_EXTRA = {
    'sleep_radius': 6,
    'build_define': ['SLEEP_ON', 'FULL_MAP_OBS'],
    'sleep_only_ablation': False,
    'full_map_observation': True,
    'base_observation_size': 206,
    'map_observation_size': 5600,
}


if __name__ == '__main__':
    train_clear.main()
