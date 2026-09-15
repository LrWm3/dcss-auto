#!/usr/bin/env python3
"""PPO sleep task with a 12x12 frontier ring, seed-0 ablation."""
import train_clear
from learn_env_sleep_explore_ring12 import Env
from learn_env import ROOT

train_clear.Env = Env
train_clear.ENV_SCOPE = 'one fixed native map; six-tile monster sleep; doubled first-seen reward; 12x12 frontier ring'
train_clear.EXTRA_SOURCES = [
    ROOT / 'scripts/learn_env_sleep.py',
    ROOT / 'scripts/learn_env_sleep_explore_ring12.py',
    ROOT / 'scripts/train_sleep_explore_ring12.py',
]
train_clear.META_EXTRA = {
    'sleep_radius': 6,
    'build_define': ['SLEEP_ON', 'EXPLORE_REWARD', 'FRONTIER_RING12_OBS'],
    'observation_size': 250,
    'frontier_ring_observation_size': 44,
    'frontier_window': 'corner-trimmed outer perimeter of player-centered 12x12 window',
    'frontier_radius': 6,
    'frontier_encoding': '1 for floor cells not yet seen in the 9x9 reward view; 0 for walls or seen floor',
    'exploration_reward': 0.002,
    'exploration_window': '9x9 floor cells, Chebyshev radius 4',
    'initial_view_rewarded': False,
}

if __name__ == '__main__':
    train_clear.main()
