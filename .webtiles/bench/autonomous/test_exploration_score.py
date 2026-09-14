import os
import unittest
from unittest.mock import patch
from exploration_score import components, learning_score, attach, VERSION
from train_model import _annotate_n_step
from counterfactual import empirical_return


class ExplorationScoreTests(unittest.TestCase):
    def test_sixty_percent_d1(self):
        r = components(0, 100 * .6)
        self.assertEqual(r['exploration_credit'], 60)
        self.assertEqual(r['training_score'], 60)

    def test_scaling_and_cap(self):
        r = components(20, 5000)
        self.assertEqual(r['native_score'], 20)
        self.assertEqual(r['exploration_credit'], 140)
        self.assertEqual(r['training_score'], 340)

    def test_native_not_overwritten(self):
        with patch.dict(os.environ, {'DCSS_EXPLORATION_SCORE': '1'}):
            r = attach({'score': 20, 'exploration_raw': 60})
        self.assertEqual(r['score'], 20)
        self.assertEqual(learning_score(r), 260)
        self.assertEqual(learning_score({'score': 20}), 20)

    def test_missing_engine_data_fails(self):
        with patch.dict(os.environ, {'DCSS_EXPLORATION_SCORE': '1'}):
            with self.assertRaises(ValueError):
                attach({'score': 0})

    def test_invalid_numbers(self):
        for n, e in ((-1, 0), (0, -1), (float('nan'), 1), (0, float('inf'))):
            with self.assertRaises(ValueError):
                components(n, e)

    def test_replay_uses_exploration_delta(self):
        rows = [{'score_before': 0, 'score_after': 0,
                 'training_score_before': 20, 'training_score_after': 30,
                 'next_observation': {}, 'terminal': False}]
        _annotate_n_step(rows, {'score': 0, **components(0, 30)})
        self.assertGreater(rows[0]['n_step_reward'], 0)

    def test_counterfactual_units(self):
        native = {'score': 0, 'score_status': 'cutoff_official'}
        new = {**native, **components(0, 60)}
        self.assertEqual(empirical_return([new, new], 2), 60)
        self.assertIsNone(empirical_return([native, new], 2))
