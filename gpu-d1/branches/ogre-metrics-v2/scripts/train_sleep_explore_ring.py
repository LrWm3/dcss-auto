#!/usr/bin/env python3
"""PPO sleep task with doubled novelty reward and a local frontier preview."""
import train_clear
from learn_env_sleep_explore_ring import Env
from learn_env import ROOT

train_clear.Env = Env
train_clear.ENV_SCOPE = 'one fixed native map; six-tile monster sleep; doubled first-seen reward; 11x11 frontier ring'
train_clear.EXTRA_SOURCES = [
    ROOT / 'scripts/learn_env_sleep.py',
    ROOT / 'scripts/learn_env_sleep_explore_ring.py',
    ROOT / 'scripts/train_sleep_explore_ring.py',
]
train_clear.META_EXTRA = {
    'sleep_radius': 6,
    'build_define': ['SLEEP_ON', 'EXPLORE_REWARD', 'FRONTIER_RING_OBS'],
    'observation_size': 246,
    'frontier_ring_observation_size': 40,
    'frontier_window': 'outer ring of player-centered 11x11 window',
    'frontier_encoding': '1 for floor cells not yet seen in the 9x9 reward view; 0 for walls or seen floor',
    'exploration_reward': 0.002,
    'exploration_window': '9x9 floor cells, Chebyshev radius 4',
    'initial_view_rewarded': False,
}


if __name__ == '__main__':
    train_clear.main()
