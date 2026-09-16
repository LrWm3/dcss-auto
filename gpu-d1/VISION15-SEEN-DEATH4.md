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
