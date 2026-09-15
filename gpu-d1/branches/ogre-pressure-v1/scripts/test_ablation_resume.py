"""Replay a completed baseline smoke run with an interruption at 256 decisions.

Usage: python test_ablation_resume.py /path/to/completed/smoke-suite
Uses a temporary directory and the existing smoke library/corpus.
"""
import json
import pathlib
import shutil
import sys
import tempfile

import torch
from ablation_storage import Store
from run_ring_ablations import GIB, library_key, worker


class Interrupted(Exception):
    pass


def main():
    reference = pathlib.Path(sys.argv[1])
    manifest = json.loads((reference / 'manifest.json').read_text())
    variant = sys.argv[2] if len(sys.argv) > 2 else 'baseline'
    job = next(j for j in manifest['jobs'] if j['name'] == variant)
    assert job['steps'] == 512 and job['batch'] == 8, 'Requires a smoke suite'
    with tempfile.TemporaryDirectory(prefix='ablation-resume-test-') as tmp:
        store = Store(tmp, 2*GIB, 5*GIB)
        (store.root / 'build').mkdir()
        for suffix in ('.so', '.sha256'):
            name = library_key(job) + suffix
            shutil.copyfile(reference / 'build' / name, store.root / 'build' / name)
        atomic = store.atomic

        def interrupt_after_save(relative, writer, max_size):
            atomic(relative, writer, max_size)
            if pathlib.Path(relative).name == 'latest.pt':
                saved = torch.load(store.root / relative, map_location='cpu', weights_only=False)
                if saved['decisions'] == 256:
                    raise Interrupted()

        store.atomic = interrupt_after_save
        try:
            worker(store, manifest, job)
            raise AssertionError('Interruption did not trigger')
        except Interrupted:
            pass
        store.atomic = atomic
        assert worker(store, manifest, job) == 0
        path = pathlib.Path('runs') / job['id'] / 'latest.pt'
        actual = torch.load(store.root / path, map_location='cpu', weights_only=False)
        expected = torch.load(reference / path, map_location='cpu', weights_only=False)
        for key in ('model', 'optimizer'):
            def equal(a, b):
                if isinstance(a, torch.Tensor):
                    assert torch.equal(a, b), key
                elif isinstance(a, dict):
                    assert a.keys() == b.keys()
                    for k in a:
                        equal(a[k], b[k])
                elif isinstance(a, (list, tuple)):
                    assert len(a) == len(b)
                    for x, y in zip(a, b):
                        equal(x, y)
                else:
                    assert a == b
            equal(actual[key], expected[key])
        for key in ('env_state', 'env_obs', 'env_mask', 'torch_rng', 'cuda_rng', 'training_stats'):
            assert torch.equal(actual[key], expected[key]), key
        assert actual['history'][-1]['sampled'] == expected['history'][-1]['sampled']
    print('PASS: interrupted resume exactly matches uninterrupted smoke training')


if __name__ == '__main__':
    main()
