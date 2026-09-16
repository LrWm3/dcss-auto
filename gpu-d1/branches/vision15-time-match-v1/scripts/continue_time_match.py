"""Continue the no-travel checkpoint to the travel arm's measured training time."""
import argparse
import fcntl
import json
import pathlib
import shutil

import torch
import run_ring_ablations as runner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if output == source:
        raise ValueError('Use a separate output to preserve the original experiment')
    output.mkdir(parents=True, exist_ok=True)
    store = runner.Store(output, 2*runner.GIB, 5*runner.GIB)
    with (output/'.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sources = {p: runner.digest(runner.ROOT/p) for p in runner.SOURCE_FILES}
        sources['scripts/continue_time_match.py'] = runner.digest(pathlib.Path(__file__))
        if not (output/'manifest.json').exists():
            if any(p.name != '.lock' for p in output.iterdir()):
                raise ValueError('Incomplete initialization: use a fresh output directory')
            original = json.loads((source/'manifest.json').read_text())
            # This branch changes only training termination, not the simulator or model.
            for p in runner.SOURCE_FILES:
                if p != 'scripts/run_ring_ablations.py' and sources[p] != original['sources'][p]:
                    raise ValueError(f'Source mismatch: {p}')
            if runner.corpus_manifest(pathlib.Path(original['corpus'])) != original['maps']:
                raise ValueError('Corpus changed')
            job = next(j.copy() for j in original['jobs'] if j['name']=='vision15_no_travel')
            travel = json.loads((source/'runs/vision15_travel-seed0/result.json').read_text())
            checkpoint = source/'runs'/job['id']/'latest.pt'
            saved = torch.load(checkpoint, map_location='cpu', weights_only=False)
            if saved['job'] != job:
                raise ValueError('Source checkpoint job mismatch')
            target = travel['train_seconds']
            if target <= saved['train_seconds']:
                raise ValueError('No additional training needed')
            provenance = dict(source=str(source), checkpoint_sha256=runner.digest(checkpoint),
                              initial_decisions=saved['decisions'], initial_train_seconds=saved['train_seconds'],
                              target_train_seconds=target, additional_train_seconds=target-saved['train_seconds'],
                              original_manifest=original)
            job.update(steps=100_000_000, train_seconds_limit=target)
            saved['job'] = job
            store.atomic(pathlib.Path('runs')/job['id']/'latest.pt', lambda f: torch.save(saved,f),128*runner.MIB)
            key = runner.library_key(job)
            (output/'build').mkdir()
            for suffix in ('.so','.sha256'):
                shutil.copy2(source/'build'/(key+suffix), output/'build'/(key+suffix))
            manifest = dict(original, jobs=[job], sources=sources)
            store.json('continuation.json', provenance)
            store.json('manifest.json', manifest)
        manifest = json.loads((output/'manifest.json').read_text())
        if manifest['sources'] != sources:
            raise ValueError('Continuation source changed')
        job = manifest['jobs'][0]
        if (output/'runs'/job['id']/'result.json').exists():
            print('Already complete')
            return 0
        return runner.worker(store, manifest, job)


if __name__ == '__main__':
    raise SystemExit(main())
