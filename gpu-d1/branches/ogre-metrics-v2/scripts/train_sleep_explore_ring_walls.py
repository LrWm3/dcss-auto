#!/usr/bin/env python3
"""PPO sleep task with known walls added to the 11x11 ring."""
import train_clear
from learn_env_sleep_explore_ring_walls import Env
from learn_env import ROOT

train_clear.Env = Env
train_clear.ENV_SCOPE = 'one fixed native map; six-tile monster sleep; doubled first-seen reward; 11x11 ring with known walls'
train_clear.EXTRA_SOURCES = [
    ROOT / 'scripts/learn_env_sleep.py',
    ROOT / 'scripts/learn_env_sleep_explore_ring_walls.py',
    ROOT / 'scripts/train_sleep_explore_ring_walls.py',
]
train_clear.META_EXTRA = {
    'observation_revision': 2,
    'sleep_radius': 6,
    'build_define': ['SLEEP_ON', 'EXPLORE_REWARD', 'MARK_WALLS', 'FRONTIER_RING_WALLS_OBS'],
    'observation_size': 246,
    'frontier_ring_observation_size': 40,
    'frontier_window': '11x11 outer perimeter at radius 5',
    'frontier_encoding': '0 unknown regardless of hidden terrain; -1 remembered wall; +1 remembered floor',
    'history_semantics': 'seen means revealed in 9x9, not stepped on; no newly-revealed observation flag',
    'exploration_reward': 0.002,
    'exploration_window': '9x9 floor cells, Chebyshev radius 4',
    'initial_view_rewarded': False,
}

if __name__ == '__main__':
    train_clear.main()
