# Seen-floor progress input with +6 clear reward

2026-09-15. Seed 0, fresh training to 10M decisions. Compare against the completed
seen-floor-count +3 clear run. Change only the clear bonus to +6. Keep +1 kill,
-1 death, -0.001 turn cost, +0.002 new floor tile, seen-floor count / 1024, and
all other settings unchanged: 2048-turn training/evaluation, 24 normal enemies,
no ogres/travel, 15x15 wall-blocked vision, LOS-gated waking, map splits and PPO.

The compared policies have identical 959-input architecture and identical initial
weights, including the initial zero-weight progress column. Train from scratch;
do not continue the earlier +3 checkpoint. Total undiscounted kill-plus-clear
reward rises from 27 to 30. Raw shaped return is not comparable across variants.

Isolated source: `branches/vision15-seen-clear6-v1`. Native code is unchanged
from `vision15-progress-v1`; only the compile-time clear reward changes. Run:

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-seen-clear6-v1/scripts/run_screen.py
```

Retain nine compact checkpoint milestones through 10,027,008 decisions. Evaluate
sampled/greedy policies on the same 32 validation layouts x 32 episodes; test
maps untouched. Report clear/death/timeout rates, kills, mean turns and training
time. Reuse the +3 curve; one seed remains an exploratory screen.

Verification compares identical corpus hashes, job settings aside from name and
clear bonus, initial weights/outcomes, and checkpoint milestones. Paired 64-
episode simulation with the same reference-policy actions must preserve full
state, all 959 observations, masks and non-reward outputs exactly. Reward must
change by +3 precisely on clears (float32 tolerance 0.000002). Independently
check the seen-count input against the seen-floor bitmap, plus existing native
synthetic counter checks. Require kills, clears and deaths in paired validation.

Existing ignores exclude weights, build products and runtime logs. Retention
uses latest/best plus small milestone snapshots, a 2 GiB suite cap and 5 GiB
free-space reserve.

## Completed results (2026-09-16)

Reached 10,027,008 decisions. Same sampled evaluation on 1,024 episodes:

| Seen-floor-input policy | Clear | Death | Timeout | Mean turns | Mean kills | Training seconds |
|---|---:|---:|---:|---:|---:|---:|
| +3 clear | 69.53% | 29.20% | 1.27% | 508.6 | 19.75 | 73.32 |
| +6 clear | 63.96% | 34.47% | 1.56% | 491.3 | 18.73 | 71.83 |

| Decisions | +3 clear rate | +6 clear rate |
|---|---:|---:|
| 0 | 0.00% | 0.00% |
| 131,072 | 0.00% | 0.00% |
| 327,680 | 0.00% | 0.00% |
| 1,015,808 | 0.20% | 0.20% |
| 2,031,616 | 43.07% | 43.36% |
| 3,014,656 | 45.61% | 48.54% |
| 5,013,504 | 55.57% | 54.30% |
| 7,503,872 | 61.23% | 59.38% |
| 10,027,008 | 69.53% | 63.96% |

The +6 bonus finishes 5.57 percentage points below +3, with 5.27 points more
deaths and 0.29 points more timeouts. It slightly leads at 2M and 3M, then trails
at 5M, 7.5M and 10M. More clear reward did not improve this seed by 10M, even with
the seen-floor progress input. This is not a multi-seed result or a general claim
that increasing the bonus cannot help. It does not identify the behavioral or
optimization mechanism. Lower mean turns include more deaths and should not be
read as better completion efficiency.

Validation passed with identical states, all 959 observations, action masks and
non-reward outputs in the paired rollout. Reward changed only by the extra +3
on clears. Coverage: 1,277 kills, 43 clears and 19 deaths across 64 episodes.
Seen-floor counts, synthetic checks, initial weights/outcomes, map hashes,
non-reward configuration and source hashes passed. Native source is byte-identical
to the +3 progress branch; reward is set through the existing compile parameter.

New training took 71.83 seconds, excluding setup, checkpoint I/O and evaluation.
The +3 comparison was reused. Artifact: `results/vision15-seen-clear6-10m.json`,
including sampled/greedy curves, per-map statistics, timing and validation.
