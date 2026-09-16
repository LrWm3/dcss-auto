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

## Completed results

Seed 0 reached 10,027,008 decisions. All policies evaluated on the same 1,024
validation episodes with 2048 game turns.

| Kill / clear / death rewards | Clear | Death | Timeout | Mean turns | Mean kills | Training seconds |
|---|---:|---:|---:|---:|---:|---:|
| +1 / +3 / -1 | 61.52% | 37.40% | 1.07% | 473.4 | 18.35 | 69.55 |
| +0.25 / +21 / -1 | 39.65% | 59.47% | 0.88% | 515.2 | 14.09 | 70.52 |
| +1 / +84 / -1 | 30.86% | 65.33% | 3.81% | 792.4 | 12.82 | 61.20 |
| +1 / +3 / -4 | 67.29% | 30.76% | 1.95% | 533.2 | 19.51 | 69.84 |

New variant learning curve:

| Decisions | Clear | Death | Timeout | Mean turns |
|---|---:|---:|---:|---:|
| 0 | 0.00% | 39.75% | 60.25% | 1390.3 |
| 131,072 | 0.00% | 30.18% | 69.82% | 1505.3 |
| 327,680 | 0.00% | 26.17% | 73.83% | 1555.5 |
| 1,015,808 | 0.00% | 25.00% | 75.00% | 1588.5 |
| 2,031,616 | 32.91% | 60.16% | 6.93% | 760.7 |
| 3,014,656 | 0.00% | 41.89% | 58.11% | 1326.8 |
| 5,013,504 | 12.01% | 60.74% | 27.25% | 1011.3 |
| 7,503,872 | 0.00% | 34.38% | 65.62% | 1419.5 |
| 10,027,008 | 30.86% | 65.33% | 3.81% | 792.4 |

Restoring the original +1 kill reward while scaling the clear bonus to +84 did
not rescue the completion-heavy configuration by 10M. It finishes 8.79 percentage
points below the +0.25/+21 variant, and 30.66 points below the original baseline.
It also exhibits a sharp drop from 32.91% clears at 2M to zero at 3M, followed by
partial recovery. This is a non-monotonic observed learning curve, not proof of
a particular optimizer failure. Gamma, timing of reward, death/exploration costs
relative to successful outcomes and value-target magnitudes are not isolated.
A larger clear incentive does not guarantee easier learning of clears.

This remains one training seed, with unchanged PPO hyperparameters. The -4 death
penalty remains the best final clear result among these four screened variants;
no claim of multi-seed superiority is established. Larger mean episode length
for +84 does not establish better survival or effective retreat.

Paired validation passed: identical full simulator state, observations, masks
and non-reward outputs, with every reward matching the intended formula. The
64 episodes covered 1,202 kills, 39 clears and 23 deaths. Corpus, initial-policy
outcomes, checkpoint milestones and non-reward settings match the prior runs.
Source hashes match the recorded manifest. Only the new variant was trained;
training took 61.20 seconds excluding compilation, evaluation and checkpoint I/O.

Artifact: `results/vision15-rewards84-10m.json`, including full sampled/greedy
curves, per-map outcomes, checkpoint hashes, comparison curves and validation.
