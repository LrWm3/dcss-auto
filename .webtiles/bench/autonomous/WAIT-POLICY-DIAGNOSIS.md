# Why the latest V6 policy waits

Run inspected: `artifacts/v6-bootstrap-repair-02`. This investigation changes no
production policy, training data, or model weights. The scripts write diagnostic
artifacts only. Health interventions are input-only experiments, not simulated
healing or new training labels.

## Confirmed mechanism

The policy selects WAIT at safe, full-health states with no visible monsters and
legal exploration moves. Across all five cutoff states, WAIT has 67.7–95.6%
softmax probability. The engine accepts WAIT and advances a turn. Logits are
finite; reversing legal-action order preserves the action scores within 0.000002.
This is not a UI lock, invalid-action fallback, NaN, or action-index mix-up.

The network does not reliably condition resting on health:

- Sample 24 noncombat WAIT-labelled states from each of the three teacher
  demonstrations (72 total). The model chooses WAIT in all 72.
- Set HP to maximum, keeping the rest of each observation fixed and synchronizing
  both exported HP representations. The teacher now chooses MOVE in all 72.
  The model still chooses WAIT in all 72. Mean WAIT probability changes from
  91.23% to 91.51%.
- On 72 noncombat MOVE-labelled states, reducing HP to half makes the teacher
  choose WAIT in all 72. The model's action-kind choices are unchanged: 30 MOVE,
  42 WAIT before and after.

These samples are temporally correlated diagnostic examples, not 144 independent
evaluation games. They demonstrate failure to respond to the changed health
signal, not a statistical estimate of full-game success.

## Why the previous explanation was incomplete

Removing all history rescues only one of the five latest cutoff states. Changing
the recent command to MOVE gives the same result. History remains a factor for
some states, but it does not explain the latest collapse by itself.

The observation encoder includes HP, maximum HP, and HP fraction. The health
information is available; the learned decision does not use it appropriately.
Input tests support a context-dependent resting shortcut, but do not uniquely
identify which combination of terrain, inventory, and global features carries it.

## Training distribution

Reconstructed the actual 2,048 selected examples from the saved source shards,
demonstrations, and policy-rollout corrections. Recomputing every selected teacher
label produced zero mismatches. All 773 WAIT labels are injured states.

Available sampled input pool before the two class-stratified reductions:

| Label | Examples |
|---|---:|
| MOVE | 7,747 |
| WAIT | 904 |
| MELEE | 489 |
| TAKE_STAIRS_DOWN | 13 |

Final fitting set:

| Label | Examples |
|---|---:|
| MOVE | 773 |
| WAIT | 773 |
| MELEE | 489 |
| TAKE_STAIRS_DOWN | 13 |

The round-robin class sampler increases WAIT from 9.9% to 37.7%, while discarding
most MOVE examples. This is a plausible amplifier of the resting bias; its causal
contribution needs a controlled training ablation rather than being assumed.

Whole-selected-set exact-action accuracy is 1,879/2,048 (91.75%), but the model
still predicts WAIT for 103 MOVE-labelled fitting examples. High average fitting
accuracy neither verifies the healing boundary nor guarantees behavior on a new
floor. Greedy execution then makes errors persistent: when fully healed, a WAIT
barely changes the relevant observation, so the next decision is WAIT again.

## Recommended next experiment

1. Preserve representative action frequencies while reserving rare-action
   coverage; do not equalize WAIT and MOVE through bulk subsampling.
2. Give healing transitions balanced *within-context* coverage, including the
   first full-health decision after a rest, rather than counting many consecutive
   resting turns as independent evidence.
3. Expose explicit HP deficit and full-health features alongside raw HP/ratio.
   These describe state; they do not forbid tactical waiting or hardcode an action.
4. Require held-out paired health-sensitivity checks and fresh-seed navigation
   before accepting another bootstrap. Do not launch another long RL run yet.

Artifacts under the inspected run:

- `wait-diagnosis.json`: input ablations and reconstructed label distribution.
- `wait-health-diagnosis.json`: paired HP interventions.
- `wait-dispatch-check.json`: finite-logit, action-order, and dispatch checks.
