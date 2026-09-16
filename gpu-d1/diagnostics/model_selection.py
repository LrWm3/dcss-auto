"""Optional explicit model-pair configuration; historical defaults stay unchanged.

DCSS_DIAGNOSTIC_MODELS points to JSON with ordinary/mixed checkpoint paths and a
nonempty result_prefix. This keeps reruns from overwriting historical results.
"""
import json
import os
import pathlib
import re

_CONFIG=None

def configuration():
    global _CONFIG
    path=os.environ.get('DCSS_DIAGNOSTIC_MODELS')
    if path is None:return None
    if _CONFIG is None:
        value=json.loads(pathlib.Path(path).read_text())
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*-',value['result_prefix']):
            raise ValueError('Diagnostic result_prefix must be a safe nonempty prefix ending in -')
        for key in ['ordinary','mixed']:
            value[key]=pathlib.Path(value[key]).resolve()
            if not value[key].is_file():raise ValueError(f'Missing checkpoint: {value[key]}')
        _CONFIG=value
    return _CONFIG

def select_models(defaults):
    config=configuration()
    return {key:config[key] for key in defaults} if config else defaults

def result_path(root,name):
    config=configuration()
    return root/'results'/((config['result_prefix'] if config else '')+name)
