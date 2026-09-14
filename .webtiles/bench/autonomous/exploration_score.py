"""Versioned lab objective; native score is never overwritten."""
import math
import os

VERSION = 'native-x10-exploration-capped-v1'


def components(native, raw):
    native, raw = float(native), float(raw)
    if not all(math.isfinite(x) and x >= 0 for x in (native, raw)):
        raise ValueError('invalid score components')
    credit = min(raw, 100. + 2. * native)
    return {'score_version': VERSION, 'native_score': native,
            'scaled_native_score': 10. * native, 'exploration_raw': raw,
            'exploration_credit': credit, 'exploration_cap': 100. + 2. * native,
            'training_score': 10. * native + credit}


def attach(state):
    if os.environ.get('DCSS_EXPLORATION_SCORE') != '1':
        return state
    if state.get('exploration_raw') is None or state.get('score') is None:
        raise ValueError('exploration objective requires engine coverage and native score')
    return {**state, **components(state['score'], state['exploration_raw'])}


def learning_score(row):
    """Historical scores retain their units; callers must not mix objectives."""
    if row.get('score_version') == VERSION:
        return row.get('training_score')
    return row.get('score')


def report_fields(state):
    keys = ('score_version', 'native_score', 'scaled_native_score', 'exploration_raw',
            'exploration_credit', 'exploration_cap', 'training_score')
    return {k: state[k] for k in keys if k in state}
