#!/usr/bin/env python3
"""PPO corrected ring task with a doubled 512-decision episode deadline."""
import train_clear
from learn_env_sleep_explore_ring_walls_512 import Env
from learn_env import ROOT

train_clear.Env = Env
train_clear.ENV_SCOPE = 'one fixed native map; six-tile monster sleep; doubled first-seen reward; corrected 11x11 ring; 512-decision deadline'
train_clear.EXTRA_SOURCES = [
    ROOT / 'scripts/learn_env_sleep.py',
    ROOT / 'scripts/learn_env_sleep_explore_ring_walls.py',
    ROOT / 'scripts/learn_env_sleep_explore_ring_walls_512.py',
    ROOT / 'scripts/train_sleep_explore_ring_walls_512.py',
]
train_clear.META_EXTRA = {
    'observation_revision': 2,
    'decision_deadline': 512,
    'sleep_radius': 6,
    'build_define': ['SLEEP_ON', 'EXPLORE_REWARD', 'MARK_WALLS', 'FRONTIER_RING_WALLS_OBS'],
    'observation_size': 246,
    'frontier_ring_observation_size': 40,
    'frontier_window': '11x11 outer perimeter at radius 5',
    'frontier_encoding': '0 unknown regardless of hidden terrain; -1 remembered wall; +1 remembered floor',
    'history_semantics': 'seen means revealed in 9x9, not stepped on; no newly-revealed observation flag',
    'exploration_reward': 0.002,
    'exploration_window': '9x9 floor cells, Chebyshev radius 4; walls are also remembered',
    'initial_view_rewarded': False,
}

if __name__ == '__main__':
    train_clear.main()
