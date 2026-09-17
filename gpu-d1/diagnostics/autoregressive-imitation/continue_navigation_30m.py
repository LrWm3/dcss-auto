"""Continue navigation-only anchoring from 10M to 30M, then repeat test evaluation."""
import fcntl
import json
import pathlib
import subprocess
import sys
import time

import torch
import episode_credit as ec
import run_ring_ablations as runner

ROOT = ec.ROOT
SOURCE = ROOT / 'learning-runs/autoregressive-anchor-navigation'
SUITE = ROOT / 'learning-runs/autoregressive-anchor-navigation-30m'
IDENT = 'navigation1-seed0'
OUTPUT = 'autoregressive-anchor-navigation-30m'


def main():
    torch.set_num_threads(1)
    SUITE.mkdir(parents=True, exist_ok=True)
    store = runner.Store(SUITE, 3 * runner.GIB, 10 * runner.GIB)
    with (SUITE / '.pipeline.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        start = time.monotonic()
        try:
            old = json.loads((SOURCE / 'manifest.json').read_text())
            original = next(j for j in old['jobs'] if j['id'] == IDENT)
            checkpoint = SOURCE / 'runs' / IDENT / 'latest.pt'
            saved = torch.load(checkpoint, map_location='cpu', weights_only=False)
            assert saved['job'] == original and saved['decisions'] == 10000384
            job = dict(original, steps=30_000_000,
                       evaluation_steps=[20_000_000, 30_000_000],
                       source_train_seconds=saved['train_seconds'])
            assert job['anchor_kind'] == 'policy' and job['anchor_weight'] == 1.
            assert job['anchor_scope'] == 'no_visible_awake_enemy'
            assert job['entropy'] == 0 and job['turn_reward'] == -.00001
            assert job['kill_milli'] == 0 and job['lr'] == .0003
            worker = pathlib.Path(__file__).with_name('anchor_navigation.py')
            holdout = pathlib.Path(__file__).with_name('anchor_holdout.py')
            files = [pathlib.Path(__file__), worker, holdout,
                     pathlib.Path(runner.__file__),
                     runner.ROOT / 'scripts/tactical_models.py',
                     runner.ROOT / 'scripts/imitation_anchor.py']
            manifest = dict(
                format=OUTPUT, corpus=old['corpus'], jobs=[job],
                continuation=dict(checkpoint=str(checkpoint),
                                  sha256=runner.digest(checkpoint),
                                  source_decisions=saved['decisions'],
                                  source_train_seconds=saved['train_seconds']),
                sources={str(p): runner.digest(p) for p in files})
            destination = pathlib.Path('runs') / IDENT / 'latest.pt'
            if not (SUITE / destination).exists():
                # Preserve optimizer, RNG, environments and history. The worker
                # builds its fixed reference from initial_model before resume.
                saved['job'] = job
                store.atomic(destination, lambda f: torch.save(saved, f),
                             256 * runner.MIB)
            del saved
            if (SUITE / 'manifest.json').exists():
                assert json.loads((SUITE / 'manifest.json').read_text()) == manifest, 'Source drift'
            else:
                store.json('manifest.json', manifest)
            folder = SUITE / 'runs' / IDENT
            store.json('status.json', dict(status='training', job=IDENT,
                                          started_at=time.time()))
            print('Continuing navigation-only anchor from 10M to 30M', flush=True)
            if not (folder / 'result.json').exists():
                # This wrapper installs NavigationAnchor; the plain runner would
                # incorrectly apply the anchor during combat as well.
                subprocess.run([sys.executable, str(worker), '--worker', IDENT,
                                '--output', str(SUITE), '--max-disk-gb', '3',
                                '--min-free-gb', '10'], check=True)
            result = json.loads((folder / 'result.json').read_text())
            curve = json.loads((folder / 'curve.json').read_text())
            assert result['decisions'] == 30000128
            assert [r['decisions'] for r in curve][-2:] == [20000256, 30000128]
            output = ROOT / 'results' / f'{OUTPUT}.json'
            output.write_text(json.dumps(dict(
                results={IDENT: dict(ppo=result, evaluations=curve)},
                wall_seconds=time.monotonic() - start), indent=2) + '\n')
            store.json('status.json', dict(status='test_evaluation', job=IDENT))
            subprocess.run([sys.executable, str(holdout), '--suite', SUITE.name,
                            '--jobs', IDENT, '--stage', '30000128',
                            '--output', OUTPUT + '-holdout'], check=True)
            store.json('status.json', dict(status='complete',
                                          wall_seconds=time.monotonic() - start))
            print('30M continuation and paired test evaluation complete', flush=True)
        except Exception as exc:
            store.json('status.json', dict(status='failed',
                                          failure=f'{type(exc).__name__}: {exc}',
                                          wall_seconds=time.monotonic() - start))
            raise


if __name__ == '__main__':
    main()
