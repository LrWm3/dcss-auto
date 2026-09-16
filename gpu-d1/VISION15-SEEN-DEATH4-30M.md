# Seen-floor / -4 death continuation to 30M

2026-09-16. Continue seed 0 of the seen-floor-count policy from 10,027,008 to
30,015,488 total decisions. Rewards remain +1 kill, +3 clear, -4 death,
+0.002 first-seen floor tile and -0.001 per turn. Keep 24 ordinary enemies,
no ogres or travel, 2048 physical turns, 15x15 wall-blocked vision and
LOS-gated waking. The extra observation remains seen-floor count / 1024.

Resume the full checkpoint, preserving model, optimizer, live worlds,
observations, masks, CPU/CUDA RNG, counters, training time and history.
Only the target step count changes. The launcher verifies the saved state
exactly after copying, checks corpus/source hashes, reuses the identical
native library and leaves the original checkpoint untouched. Runner changes
only add evaluation milestones at 15M, 20M and 25M.

Evaluate sampled and greedy policies at 15M, 20M, 25M and 30M on the same
32 validation maps x 32 episodes. The 256 training layouts and 100 untouched
test layouts stay unchanged. This is one continued training seed, not a
multi-seed comparison. Retain compact milestones plus latest/best under the
2 GiB suite cap and 5 GiB free-space reserve; existing ignores cover binaries,
weights and logs.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-seen-death4-30m-v1/scripts/run_continue.py
```

Source experiment: [10M results](VISION15-SEEN-DEATH4.md).
Output: `results/vision15-seen-death4-30m.json`. Training seconds are cumulative
from the original run; additional training time is also recorded separately.

## Completed results

Sampled policy, 1,024 validation episodes per checkpoint:

| Decisions | Clear | Death | Timeout | Mean turns | Mean kills | Cumulative training seconds |
|---|---:|---:|---:|---:|---:|---:|
| 10,027,008 | 70.61% | 27.73% | 1.66% | 544.8 | 20.10 | 71.18 |
| 15,007,744 | 72.66% | 25.49% | 1.86% | 536.0 | 20.29 | 108.69 |
| 20,021,248 | 72.56% | 25.88% | 1.56% | 536.6 | 20.26 | 146.22 |
| 25,001,984 | 76.37% | 21.78% | 1.86% | 545.1 | 20.91 | 183.00 |
| 30,015,488 | 78.71% | 20.41% | 0.88% | 543.0 | 21.01 | 220.03 |

Clear rate increased 8.11 percentage points from 10M to 30M. Deaths fell
7.32 points and timeouts fell 0.78 points. Mean episode length stayed near
543 turns, while kills increased from 20.10 to 21.01. Improvement continued
after the roughly flat 15M/20M checkpoints; this does not show saturation.
This establishes continued improvement for this seed, not superiority across
training seeds or on the untouched test set.

The continuation used 148.84 additional training seconds
(220.03 cumulative); wall time including evaluations and checkpoint I/O
was 202.09 seconds. State-transfer equality, unchanged source checkpoint
hash, original history prefix, corpus hashes and all five milestone checks passed.
Native simulator and observation code are unchanged from the validated 10M run.
