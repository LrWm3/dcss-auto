# Continuation to 10 million decisions

All three PPO runs continued from their 3,014,656-decision checkpoints to **10,027,008 total decisions each** (306 collection/update cycles). Task rules, architecture and PPO hyperparameters stayed fixed. Each run added 7,012,352 decisions.

On the same 2,048-episode comparison suite (root seed 1,200,000):

| Training seed | 3m sampled | 10m sampled | 3m argmax | 10m argmax |
|---:|---:|---:|---:|---:|
| 0 | 90.87% | 93.75% | 86.91% | 94.19% |
| 1 | 91.06% | 94.09% | 88.48% | 95.46% |
| 2 | 92.29% | 94.34% | 90.97% | 95.41% |

Random legal actions clear 45.70% and shortest-path pursuit clears 91.50% on this suite. Every extended policy has a higher observed clear rate than its 3m predecessor, and all now exceed pursuit's observed rate. This remains a three-training-seed, single-map experiment; it is not evidence of broader Crawl competence. The comparison suite was already evaluated at 3m, so this is repeated evaluation on that suite, not a newly untouched test set. Per-policy Wilson intervals and other metrics are in [fresh-test.json](results/learning-v1-10m/fresh-test.json).

The sampled-policy mean clear rate rose from 91.41% to 94.06%, a gain of 2.65 percentage points. All final policies had zero timeouts on this suite. Improvement continues, but it is smaller than the early gains. These checkpoints do not establish the eventual plateau.

![Extended learning curve](results/learning-v1-10m/learning-curve.svg)

The separate 1,024-episode monitoring suite produced sampled clear rates of 91.7–92.7% near 5m and 94.2–95.3% at 10m. Final argmax monitoring rates were 94.7–95.0%.

The extension took **34.58–35.24 additional seconds of training-loop time per run**. Cumulative training-loop time, including the original 3m segment, is 50.07–50.47 seconds per run. As before, these synchronized timings include simulation, policy inference, GAE and optimization, and exclude startup, evaluation and checkpoint writes.

## Resume boundary and validation

Legacy 3m checkpoints contained model weights, Adam state, and PyTorch CPU/CUDA sampling RNG states, but omitted live environments. These were restored, and the 512 environments restarted from fresh episode seeds 4,000,000 / 4,100,000 / 4,200,000 for training seeds 0 / 1 / 2. Partial episodes at the boundary were discarded. This is a continuation of learning with fresh episodes, not an exact uninterrupted replay. Per-run `seed-*-resume.json` files record the boundary.

New checkpoints additionally save live simulator state (including environment RNGs), observations and action masks. A new [resume test](results/learning-v1-10m-resume-test.log) compared a short uninterrupted PPO run with a split/resumed run and found exact agreement in weights, optimizer state, live worlds, observations, masks and sampling RNGs. The continuation also checks task-source fingerprints and training hyperparameters before resuming. Original 3m artifacts were preserved.

## Reproduce or extend

```sh
gpu-d1/.venv/bin/python gpu-d1/scripts/train_clear.py \
  --enemies 8 --steps 10000000 --seeds 0,1,2 \
  --resume-from gpu-d1/learning-runs/clear-v1 \
  --output gpu-d1/learning-runs/clear-v1-10m-reproduction

gpu-d1/.venv/bin/python gpu-d1/scripts/report_learning.py \
  gpu-d1/learning-runs/clear-v1-10m-reproduction \
  --output gpu-d1/results/learning-v1-10m-reproduction

gpu-d1/.venv/bin/python gpu-d1/scripts/test_resume.py
```

`--steps` is the cumulative target, not additional decisions. `--resume-from` points to a run directory, selecting each seed's last recorded checkpoint. Use a new output directory. Further continuation from `learning-runs/clear-v1-10m` restores live environments too. The combined curve retains the earlier rows, whose checkpoints remain in the parent run directory.

The completed new checkpoints are `learning-runs/clear-v1-10m/seed-{0,1,2}/policy-10027008.pt`. Configuration, resume provenance, combined curves, evaluation results and plots are archived under [results/learning-v1-10m/](results/learning-v1-10m/).
