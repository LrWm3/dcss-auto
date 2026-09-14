import unittest

from train_model import _annotate_n_step, _td_target, FeatureCache
from model import ActionValueModel


def observation(score, terminal=False):
    return {
        'schema': 'crawl-general-v1',
        'score': score, 'score_status': 'live_official',
        'terminal': 'death' if terminal else False,
        'actions': [] if terminal else [{'kind': 'WAIT'}],
        'player': {'hp': 10, 'max_hp': 10},
    }


class LearningTargetTests(unittest.TestCase):
    def test_short_horizon_targets_use_live_score_changes(self):
        rows = [
            {'observation': observation(0), 'score_before': 0,
             'score_after': 0, 'next_observation': observation(0),
             'terminal': False, 'return': 10},
            {'observation': observation(0), 'score_before': 0,
             'score_after': 10, 'next_observation': observation(10, True),
             'terminal': True, 'return': 10},
        ]
        _annotate_n_step(rows, {'score': 10})
        self.assertTrue(rows[0]['n_step_score_observed'])
        self.assertTrue(rows[0]['n_step_terminal'])
        self.assertGreater(rows[0]['n_step_reward'], 0)
        target = _td_target(ActionValueModel(), rows[0], FeatureCache())
        self.assertAlmostEqual(target, __import__('math').log1p(10))


if __name__ == '__main__':
    unittest.main()
