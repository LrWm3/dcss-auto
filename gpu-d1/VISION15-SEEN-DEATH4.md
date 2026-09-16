# Seen-floor progress input with -4 death penalty

2026-09-16. Fresh seed-0 training to 10M decisions, with +1 kill, +3 clear and -4
death. The only change from the completed seen-floor +3-clear/-1-death run is
the death penalty. Keep seen-floor count / 1024, +0.002 new-floor reward, -0.001
turn cost, 2048-turn training/evaluation, 24 normal enemies, no ogres/travel,
15x15 wall-blocked vision, LOS-gated waking, PPO and map splits unchanged.

Reuse the existing seen-floor/-1 and no-progress/-1 and /-4 curves. This fills
out a single-seed comparison of progress input versus death penalty, with +3
clear reward in every case. New and seen-floor/-1 policies have identical 959-
input architectures and initial weights, including the initial zero-weight
progress column. No prior weights are used to warm-start training.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-seen-death4-v1/scripts/run_screen.py
```

The isolated branch preserves previous source and artifacts. Native source is
identical to the prior progress experiments; the existing DEATH_MILLI compile
parameter sets the penalty. Nine checkpoints through 10,027,008 decisions,
sampled/greedy evaluations on 32 validation maps x 32 episodes. Test set untouched.

Checks: same corpus and job settings except name/death penalty, matching initial
weights/outcomes and checkpoints; paired 64-episode stepping with identical
reference-policy actions must yield identical full simulator states, all 959
observations, masks and non-reward outputs. Reward must differ by exactly -3 on
deaths (float32 tolerance 0.000002), with kill/clear/death coverage required.
Seen-floor inputs are checked against the bitmap, with synthetic counter tests.

Report clears, deaths, timeouts, kills, mean turns and training time. Raw shaped
return is not directly comparable across penalties; one seed is exploratory.
Existing ignores cover weights, libraries and logs. Keep latest/best plus compact
milestones under the 2 GiB suite cap, with 5 GiB free-space reserve.

## Completed results

New policy reached 10,027,008 decisions. Sampled evaluation on the same 1,024
validation episodes, all with +1 kill and +3 clear reward:

| Seen-floor input | Death penalty | Clear | Death | Timeout | Mean turns | Mean kills | Training seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| No | -1 | 61.52% | 37.40% | 1.07% | 473.4 | 18.35 | 69.55 |
| No | -4 | 67.29% | 30.76% | 1.95% | 533.2 | 19.51 | 69.84 |
| Yes | -1 | 69.53% | 29.20% | 1.27% | 508.6 | 19.75 | 73.32 |
| Yes | -4 | 70.61% | 27.73% | 1.66% | 544.8 | 20.10 | 71.18 |

Seen-floor-input learning curves:

| Decisions | Death -1 clear rate | Death -4 clear rate |
|---|---:|---:|
| 0 | 0.00% | 0.00% |
| 131,072 | 0.00% | 0.00% |
| 327,680 | 0.00% | 0.00% |
| 1,015,808 | 0.20% | 0.00% |
| 2,031,616 | 43.07% | 50.49% |
| 3,014,656 | 45.61% | 49.71% |
| 5,013,504 | 55.57% | 58.79% |
| 7,503,872 | 61.23% | 63.77% |
| 10,027,008 | 69.53% | 70.61% |

The combination has the highest observed final clear rate of these four runs,
but improves only 1.07 percentage points (11 episodes) over seen-floor input
with death -1. Death rate falls 1.46 points while timeouts rise 0.39 points.
This is a modest single-seed observation, not established multi-seed superiority.

Without progress input, increasing the death penalty improved clears by 5.76
points. With progress input, its observed improvement is smaller; the two gains
are not additive in this seed. This does not establish redundant mechanisms:
training randomness, different learned behaviors and evaluation variability have
not been separated. The new result is 3.32 points above death -4 without progress
and 9.08 points above neither change.

Paired 64-episode validation passed: states, all 959 observations, masks and
non-reward outputs match exactly; reward differs only by -3 on death. Coverage
includes 1,277 kills, 43 clears and 19 deaths. Count encoding, bitmap comparisons,
synthetic checks, initial weights/outcomes, corpus/settings and source hashes
passed. Native source remains byte-identical to the progress branch.

Training took 71.18 seconds, excluding setup, evaluation and checkpoint I/O.
Prior comparison runs were reused. Artifact: `results/vision15-seen-death4-10m.json`,
with full sampled/greedy curves, per-map metrics, hashes and validation results.
