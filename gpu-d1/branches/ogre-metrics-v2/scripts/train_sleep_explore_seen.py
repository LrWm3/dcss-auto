#!/usr/bin/env python3
"""PPO sleep task with doubled first-seen reward and local seen history."""
import train_clear
from learn_env_sleep_explore_seen import Env
from learn_env import ROOT

train_clear.Env = Env
train_clear.ENV_SCOPE = 'one fixed native map; six-tile monster sleep; doubled first-seen reward; local seen history'
train_clear.EXTRA_SOURCES = [
    ROOT / 'scripts/learn_env_sleep.py',
    ROOT / 'scripts/learn_env_sleep_explore_seen.py',
    ROOT / 'scripts/train_sleep_explore_seen.py',
]
train_clear.META_EXTRA = {
    'sleep_radius': 6,
    'build_define': ['SLEEP_ON', 'EXPLORE_REWARD', 'SEEN_OBS'],
    'observation_size': 287,
    'seen_observation_size': 81,
    'exploration_reward': 0.002,
    'exploration_window': '9x9 floor cells, Chebyshev radius 4',
    'initial_view_rewarded': False,
    'seen_observation': 'player-centered 9x9; 1 for floor cells already seen in this episode',
}


if __name__ == '__main__':
    train_clear.main()
