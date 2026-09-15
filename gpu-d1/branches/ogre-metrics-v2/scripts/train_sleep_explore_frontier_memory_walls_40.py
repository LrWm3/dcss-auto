#!/usr/bin/env python3
"""PPO run: corrected frontier memory, 40 enemies, 1024-decision deadline."""
import train_clear
from learn_env_sleep_explore_frontier_memory_walls_40 import Env
from learn_env import ROOT

train_clear.Env = Env
train_clear.ENV_SCOPE = 'one fixed native map; six-tile monster sleep; doubled first-seen reward; corrected frontier memory with known walls; 40 enemies; 1024-decision deadline'
train_clear.EXTRA_SOURCES = [
    ROOT / 'scripts/learn_env_sleep.py',
    ROOT / 'scripts/learn_env_sleep_explore_frontier_memory_walls_40.py',
    ROOT / 'scripts/train_sleep_explore_frontier_memory_walls_40.py',
]
train_clear.META_EXTRA = {
    'observation_revision': 2,
    'enemy_slots': 40,
    'decision_deadline': 1024,
    'history_semantics': 'seen means revealed in 9x9, not stepped on; no newly-revealed observation flag',
    'sleep_radius': 6,
    'build_define': ['LEARN_ENEMIES=40', 'SLEEP_ON', 'EXPLORE_REWARD', 'MARK_WALLS', 'FRONTIER_MEMORY_WALLS_OBS'],
    'observation_size': 373,
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
