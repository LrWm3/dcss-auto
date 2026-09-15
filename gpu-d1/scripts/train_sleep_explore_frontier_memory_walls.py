#!/usr/bin/env python3
"""PPO sleep task with nearest-frontier memory and known wall marks."""
import train_clear
from learn_env_sleep_explore_frontier_memory_walls import Env
from learn_env import ROOT

train_clear.Env = Env
train_clear.ENV_SCOPE = 'one fixed native map; six-tile monster sleep; doubled first-seen reward; frontier memory with known walls'
train_clear.EXTRA_SOURCES = [
    ROOT / 'scripts/learn_env_sleep.py',
    ROOT / 'scripts/learn_env_sleep_explore_frontier_memory_walls.py',
    ROOT / 'scripts/train_sleep_explore_frontier_memory_walls.py',
]
train_clear.META_EXTRA = {
    'observation_revision': 2,
    'history_semantics': 'seen means revealed in 9x9, not stepped on; no newly-revealed observation flag',
    'sleep_radius': 6,
    'build_define': ['SLEEP_ON', 'EXPLORE_REWARD', 'MARK_WALLS', 'FRONTIER_MEMORY_WALLS_OBS'],
    'observation_size': 213,
    'frontier_memory_observation_size': 7,
    'frontier_definition': 'nearest seen floor cell adjacent to at least one unknown cell; remembered walls are excluded',
    'frontier_distance': 'shortest-path distance on the fixed floor map',
    'frontier_encoding': 'valid, anchor dx/dy, path distance, unknown-neighbor count, one unknown-neighbor dx/dy',
    'exploration_reward': 0.002,
    'exploration_window': '9x9 floor cells, Chebyshev radius 4; walls are also remembered',
    'initial_view_rewarded': False,
}

if __name__ == '__main__':
    train_clear.main()
