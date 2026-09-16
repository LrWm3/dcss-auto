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
