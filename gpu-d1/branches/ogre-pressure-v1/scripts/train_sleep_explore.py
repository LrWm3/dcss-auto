#!/usr/bin/env python3
"""PPO sleep task with a once-per-episode first-seen-floor reward."""
import train_clear
from learn_env_sleep_explore import Env
from learn_env import ROOT

train_clear.Env = Env
train_clear.ENV_SCOPE = 'one fixed native map; six-tile monster sleep; first-seen floor-cell reward'
train_clear.EXTRA_SOURCES = [
    ROOT / 'scripts/learn_env_sleep.py',
    ROOT / 'scripts/learn_env_sleep_explore.py',
    ROOT / 'scripts/train_sleep_explore.py',
]
train_clear.META_EXTRA = {
    'sleep_radius': 6,
    'build_define': ['SLEEP_ON', 'EXPLORE_REWARD'],
    'sleep_only_ablation': False,
    'exploration_reward': 0.001,
    'exploration_window': '9x9 floor cells, Chebyshev radius 4',
    'initial_view_rewarded': False,
}


if __name__ == '__main__':
    train_clear.main()
