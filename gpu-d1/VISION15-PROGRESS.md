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
