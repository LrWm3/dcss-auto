# Explicit progress inputs with +3 clear reward

2026-09-15. Two new policies trained from initialization to 10M decisions, seed 0.
Reuse the completed fixed-2048 baseline for no extra progress input. All variants
use +1 kill, +3 clear, -1 death, -0.001 per turn and +0.002 newly seen floor tile.
Same 2048 physical turns in training and validation, 24 normal enemies, no ogres,
no travel, 15x15 wall-blocked vision, LOS-gated waking, PPO and map splits.

| Variant | Additional input |
|---|---|
| Existing baseline | None |
| enemies_left | (24 - kills so far) / 24 |
| tiles_seen | Number of distinct floor tiles seen at least once / 1024 |

Remaining-enemy count is privileged information about enemies anywhere on the
floor; it discloses no locations. Seen-floor count is available from the player's
accumulated observations. It counts floor, not walls, consistent with the existing
exploration reward. It is neither tiles stepped on nor percentage of map explored.
1024 is a fixed scale for every map: the hidden total floor area is not used.
Counters reset with each episode; initial visible floor already contributes to
seen-floor count. The existing elapsed-time input is unchanged.

Both new models append one scalar after the original 958 observations. Original
feature indices, including current-visibility cells, remain unchanged. The first
layer is initialized exactly as the original 958-input policy, then extended with
a zero-weight column without consuming RNG. All other initial weights match.
The scalar's weights are trainable; both variants have identical parameter count.
The original baseline has 128 fewer weights, but the initial function is matched.
No baseline retraining is necessary for this first-pass screen; subsequent
training is not expected to remain bit-identical across input dimensions.

Implementation: `branches/vision15-progress-v1`. Source branches for old
experiments remain untouched. Run:

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-progress-v1/scripts/run_screen.py
```

Nine checkpoint milestones, sampled and greedy evaluation on 32 held-out
validation maps x 32 episodes. Test set untouched. Compare clear/death/timeout
rates, kills and episode lengths. This tests whether progress inputs help with
baseline rewards; it does not test their interaction with +21 or +84 bonuses.
Seen-floor count is a proxy for exploration progress, not a direct predictor of
how many enemies remain. One seed is exploratory.

Verification: identical non-observation settings, rewards and corpus hashes;
matching initialization and initial-policy outcome metrics; synthetic native
observation checks for every remaining-enemy count from 0 through 24, plus seen
counts 512 and 1234; paired 64-episode stepping against the unchanged simulator
with full state, original observation prefix, masks, rewards and outputs equal.
The extra scalar is independently checked against actual living-monster counts
or the seen-floor bitmap. Require coverage of kills, clears and deaths.

Retention uses existing bounded latest/best and compact milestone snapshots,
2 GiB suite cap and 5 GiB free-space reserve. Existing ignores cover weights,
compiled libraries and runtime logs. Compact JSON summaries are tracked.

## Completed results

Both variants reached 10,027,008 decisions. Sampled policy, same 1,024 validation
episodes per checkpoint, 2048-turn evaluation limit.

| Added progress input | Clear | Death | Timeout | Mean turns | Mean kills | Training seconds |
|---|---:|---:|---:|---:|---:|---:|
| None (reused baseline) | 61.52% | 37.40% | 1.07% | 473.4 | 18.35 | 69.55 |
| Enemies remaining | 68.26% | 30.76% | 0.98% | 499.2 | 19.42 | 71.19 |
| Unique floor tiles seen | 69.53% | 29.20% | 1.27% | 508.6 | 19.75 | 73.32 |

Clear-rate learning curves:

| Decisions | None | Enemies remaining | Floor tiles seen |
|---|---:|---:|---:|
| 0 | 0.00% | 0.00% | 0.00% |
| 131,072 | 0.00% | 0.00% | 0.00% |
| 327,680 | 0.00% | 0.00% | 0.00% |
| 1,015,808 | 0.00% | 0.00% | 0.20% |
| 2,031,616 | 40.72% | 44.82% | 43.07% |
| 3,014,656 | 46.09% | 54.30% | 45.61% |
| 5,013,504 | 54.88% | 59.77% | 55.57% |
| 7,503,872 | 58.20% | 64.45% | 61.23% |
| 10,027,008 | 61.52% | 68.26% | 69.53% |

Remaining-enemy count improves final clear rate by 6.74 percentage points over
the baseline; seen-floor count improves it by 8.01 points. Most of the difference
comes from fewer deaths, with timeouts near 1%. Seen-floor count trails enemy
count at intermediate milestones and finishes 1.27 points higher; one seed is
insufficient to rank these inputs reliably or establish robustness.

The results are consistent with useful progress information being absent from
the baseline. They do not establish that the policies understand the clear
condition, nor that missing progress caused the previous +21/+84 reward failures.
The new scalar could affect exploration, combat risk or state-value estimation.
Reward-by-observation interactions require a separate experiment. All earlier
reward experiments remain valid measurements of those observation/reward setups.

Both variants passed the paired 64-episode checks: full state, original 958 input
values, masks, rewards and outputs matched the unchanged simulator exactly.
Each comparison included 1,202 kills, 39 clears and 23 deaths. Counts were checked
against actual living-enemy arrays and the seen-floor bitmap; encoded integers
matched exactly, including resets. Synthetic counter tests, initial model weight
and outcome equality, corpus hashes and source hashes all passed.

The first validation attempt used bit-exact comparison between CUDA and Torch
division by 24. It rejected a 5.96e-8 rounding difference. Validation now requires
exact recovery of the integer count and a normalized-value difference <=1e-7;
the floor-count input matches exactly. No simulator or trained policy changed,
and completed training was reused when rerunning validation. The result's
wall_seconds measures this final orchestrator pass, not original training plus
validation wall time. Training times above retain the full measured training.

Artifact: `results/vision15-progress-10m.json`, with complete sampled/greedy
curves, per-map outcomes, checkpoint hashes and validation results.
