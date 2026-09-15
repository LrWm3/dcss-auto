#!/usr/bin/env python3
"""PPO corrected ring-plus-frontier task with a 512-decision deadline."""
import train_clear
from learn_env_sleep_explore_ring_memory_walls_512 import Env
from learn_env import ROOT

train_clear.Env = Env
train_clear.ENV_SCOPE = 'one fixed native map; six-tile monster sleep; doubled first-seen reward; corrected 11x11 ring plus frontier memory with known walls; 512-decision deadline'
train_clear.EXTRA_SOURCES = [
    ROOT / 'scripts/learn_env_sleep.py',
    ROOT / 'scripts/learn_env_sleep_explore_ring_memory_walls_512.py',
    ROOT / 'scripts/train_sleep_explore_ring_memory_walls_512.py',
]
train_clear.META_EXTRA = {
    'observation_revision': 2,
    'decision_deadline': 512,
    'sleep_radius': 6,
    'build_define': ['SLEEP_ON', 'EXPLORE_REWARD', 'MARK_WALLS', 'FRONTIER_RING_MEMORY_WALLS_OBS'],
    'observation_size': 253,
    'frontier_ring_observation_size': 40,
    'frontier_memory_observation_size': 7,
    'frontier_window': '11x11 outer perimeter at radius 5',
    'frontier_encoding': 'ring: 0 unknown regardless of hidden terrain; -1 remembered wall; +1 remembered floor; pointer: valid, anchor dx/dy, path distance, unknown-neighbor count, one unknown-neighbor dx/dy',
    'frontier_definition': 'nearest seen floor cell adjacent to at least one unknown cell; remembered walls are excluded',
    'frontier_distance': 'shortest-path distance on the fixed floor map',
    'history_semantics': 'seen means revealed in 9x9, not stepped on; no newly-revealed observation flag',
    'exploration_reward': 0.002,
    'exploration_window': '9x9 floor cells, Chebyshev radius 4; walls are also remembered',
    'initial_view_rewarded': False,
}

if __name__ == '__main__':
    train_clear.main()
