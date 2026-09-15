#!/usr/bin/env python3
"""PPO on the corrected ring task with a held-out multi-layout split."""
import train_clear
from learn_env_ring_multi import Env
from learn_env import ROOT

TRAIN = ROOT / 'fixtures/d1-corpus-388/train'
VALIDATION = ROOT / 'fixtures/d1-corpus-388/validation'

train_clear.Env = Env
train_clear.TRAIN_ENV_KWARGS = {'corpus': TRAIN}
train_clear.EVAL_ENV_KWARGS = {'corpus': VALIDATION}
train_clear.ENV_SCOPE = (
    '256-map D1 training split; 32-map validation split; 40 enemies; 1024 decisions; '
    'six-tile sleep; doubled first-seen floor reward; remembered walls; corrected 11x11 ring'
)
train_clear.EXTRA_SOURCES = [
    ROOT / 'scripts/learn_env_ring_multi.py',
    ROOT / 'scripts/learn_env_v2.py',
    ROOT / 'scripts/train_sleep_explore_ring_walls_multi.py',
]
train_clear.META_EXTRA = {
    'observation_revision': 3,
    'enemy_slots': 40,
    'decision_deadline': 1024,
    'sleep_radius': 6,
    'observation_size': 406,
    'frontier_window': '11x11 outer perimeter at radius 5',
    'frontier_encoding': '0 unknown; -1 remembered wall; +1 remembered floor',
    'history_semantics': 'seen means revealed in 9x9; walls are separately remembered',
    'exploration_reward': 0.002,
    'initial_view_rewarded': False,
    'train_corpus': str(TRAIN),
    'eval_corpus': str(VALIDATION),
    'test_corpus_reserved': str(ROOT / 'fixtures/d1-corpus-388/test'),
}


if __name__ == '__main__':
    train_clear.main()
