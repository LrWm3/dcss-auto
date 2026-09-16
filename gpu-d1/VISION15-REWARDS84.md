# Restore +1 kills while retaining an 84:1 clear-to-kill reward ratio

2026-09-15. Train from initialization to 10M decisions, seed 0. Reward is +1 per
kill, +84 additional for clearing, -1 for death, -0.001 per turn and +0.002 per
newly seen floor tile. Training and evaluation deadlines are 2048 physical
turns. Same 24 normal enemies, no ogres, no travel, 15x15 wall-blocked vision,
LOS-gated waking, map splits, observation clock and PPO settings as the previous
reward screen. No test maps used. Same nine checkpoint milestones.

Compare with retained baseline (+1/+3/-1), completion-focused (+0.25/+21/-1)
and death-4 (+1/+3/-4) curves. The new variant multiplies kill and clear rewards
by four relative to the earlier completion variant, but leaves death,
exploration and turn rewards unchanged. Thus this is not uniform reward scaling:
it changes their relative weights as well as the scale of returns/value targets.
Total undiscounted kill-plus-clear reward is now 24 + 84 = 108.

Implementation: isolated `branches/vision15-rewards84-v1`, using the identical
reward-parameterized simulator from `vision15-rewards-v1`. Old sources and
artifacts remain unchanged. Native compile flags, library keys, job manifest and
result provenance record the new rewards.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-rewards84-v1/scripts/run_screen.py
```

Train only the new variant. Reuse previous curves for comparison. Assert identical
non-reward job settings and corpus hashes against both baseline and completion
variant. Compare initial-policy outcomes and all checkpoint milestones. Run the
existing paired 64-episode simulator/reward test using identical baseline-policy
actions, checking full states, observations, action masks and non-reward outputs.
Verify changed rewards analytically at each step; require coverage of kills,
clears and deaths. Float32 absolute tolerance is 0.00002 for rewards near 85,
well below the 0.001 reward unit. Dynamics must still match exactly.

Evaluate sampled and greedy policies on 32 validation maps x 32 episodes. Compare
clear/death/timeout rates, kills and episode lengths; raw shaped returns are not
comparable across reward functions. One seed is an exploratory screen.

Retention: latest/best and compact milestone weights, 2 GiB suite cap with 5 GiB
free-space reserve. Existing ignores cover weights, libraries and runtime logs.
