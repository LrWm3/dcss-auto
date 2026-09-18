# Full-history recurrent reconstruction

Follow-up to NATIVE-REMEDIES.md. The earlier diagnostic found substantial
policy disagreement between short recurrent replay and live execution. Test
whether correcting that mismatch improves navigation, rather than assuming
that disagreement alone explains failure.

## Matched screen

Two seed-0 DAgger continuations from `native-curriculum-seed0/selected.pt`:

- **short**: reconstruct memory from up to 16 preceding observations.
- **full**: reconstruct memory from every preceding observation since reset.

Both use the same episode-backed buffer implementation. Reconstruct with current
encoder and recurrent weights on every update; do not cache learned features or
rollout hidden states. Prefix execution has no gradient. The following 16-step
learning chunk trains the encoder, recurrent core, and action head normally.
At episode start, both use zero memory. Padding contributes no loss and cannot
leak from later observations into earlier causal recurrent states.

All other settings match the previous balanced arm: native 80x70 maps, 15x15
local crop, coarse global map, no extra navigation hints, no enemies, pure
learner rollouts with controller labels, half expert / half learner loss,
three observation-category sampling/loss groups, fresh Adam lr1e-4, AMP scale
1024, gradient clip1, 16 sequences from each buffer per update, 2000 updates.
Retain 1024 learning chunks per buffer. Chunks reference complete collection
waves; evicting the last reference releases that wave's raw observations.
CNN prefix processing uses batches of at most 256 real frames plus padding;
recurrent history is not truncated. Raw prefix storage costs more memory, but
there is no accumulating on-disk replay. Checkpoints are latest and selected only.

Collect 32 environments, at most 512 steps, refreshing learner data every 100
updates and expert data every 500. The policy memory resets only at episode
reset. Both history variants preserve the original raw chunk order, balanced
sampling, losses, and RNG calls. On-policy trajectories diverge as weights do;
this is update-budget matched, not identical-data or wall-time matched.

Evaluate every 500 updates with a 1024-turn deadline. Select the trained checkpoint
by mean middle-band validation success (64 cases per category), then test on
middle-band and original longer-route held-out cases (128 per category, on 32
maps). Also report original longer-route validation. No test-set checkpoint
selection. The starting checkpoint remains a separate baseline; a trained
checkpoint is not automatically promoted if worse.

## Validation before training

`check_history_replay.py` compares all retained learning chunks to the original
buffer under identical collection seeds, checks short-replay loss equivalence,
and compares full-history learning logits against stepwise execution. The
latter is repeated after an optimizer update to ensure reconstruction uses
fresh weights. It also verifies detached prefix states and gradients/updates
through the trainable encoder and recurrent core. First/late chunks and a
partially padded terminal chunk are included.

## Running

Use the compiler-header CPATH from EXECUTION-OPTIMIZATION.md.

```sh
python check_history_replay.py
python native_history_suite.py
```

Reports: `results/native-history-{check,short,full}.json`.
These are supervised DAgger updates, not PPO decisions.

Preflight passed: 5,965 collected decisions, all 383 retained chunks match the
legacy buffer exactly, and sampled short-history losses both equal 1.6907693.
Full-history replay agreed on all 136 checked actions before and after one
optimizer update; maximum per-state KL was 1.09e-5 and 2.12e-5 nats respectively.
Encoder gradients and recurrent weight changes were verified. Prefix states
have no gradient. Initial checks exposed a hidden-state shape mismatch during
review and a CUDA illegal access in the large multi-input stack path; history
assembly now uses 16-frame stacks followed by concatenation. Training was gated
on the successful corrected checks.

## Short-history control results

The matched short-history run completed 2000 updates in 192.74s of training and
collection (excluding evaluation), with 123,713 collected decisions and 934,146
replayed supervised targets. No AMP updates were skipped. Its selected
checkpoint was update 1000: middle-band validation 70.31% known / 68.75% explore.
Its test results were 60.16%/62.50% on the middle band and 30.47%/50.78% on the
original longer-route set. Original longer-route validation was 20.31%/42.19%.

This newly executed control is the primary comparator for full history. Its
initial raw chunks and tested loss match the old implementation exactly, but
small numerical changes from prefix batching can change subsequent greedy
trajectories and optimization. The previous balanced run is not substituted
for this matched control. There is one training seed per arm.

## Full-history results and comparison

The full-history arm completed 2000 updates in 216.39s of training and collection,
12.3% longer than short replay. It collected 123,605 decisions and used 930,266
replayed supervised targets, with zero AMP skips. It encoded 7,116,000 real
prefix frames versus 681,024 for short replay. Total training plus collection
cost rises much less than prefix work alone because other work remains shared.
Observed GPU usage was about 6 GB. Initial evaluation, compilation before the
training timer, and validation/test evaluation are additional wall time.

All results below use validation-selected checkpoints: short update 1000,
full update 500. The starting checkpoint is shown separately.

| Held-out evaluation | Starting checkpoint | Short replay | Full replay |
|---|---:|---:|---:|
| Middle known-stair success | 64.84% | 60.16% | 75.78% |
| Middle exploration success | 69.53% | 62.50% | 64.06% |
| Original longer-route known-stair success | 31.25% | 30.47% | 35.94% |
| Original longer-route exploration success | 56.25% | 50.78% | 40.62% |

There are 128 cases per condition, on 32 held-out maps. Compared with short
replay, full replay changes 27 middle known-stair failures into successes and
7 successes into failures. Compared with the starting checkpoint, it gains 24
and loses 10. Middle exploration gains 23/loses 21 versus short replay, and
gains 15/loses 22 versus the source. The paired longer-route counts are saved in
`results/native-history-paired.json`; known-stair gains 24/loses 17 and exploration
gains 26/loses 39 relative to short replay. Cases on a shared map are correlated;
this is a one-seed screen, not a multi-seed significance claim.

On middle known-stair cases, mean additional turns fall from 417.20 to 278.66,
and reversals from 304.02 to 179.38, comparing short to full replay. The benefit
therefore includes less looping, not merely a different terminal outcome.
On longer-route exploration, turns instead rise from 587.18 to 674.56 and
reversals from 326.84 to 398.88. All failures are timeouts; these maps have no
enemies. The coarse representation and individual action set are unchanged.

Original longer-route validation also exhibits a tradeoff: short 20.31% known /
42.19% explore, full 29.69%/34.38%. Middle-band validation over training:

| Update | Short known / explore | Full known / explore |
|---|---:|---:|
| Before training | 64.06% / 68.75% | 64.06% / 68.75% |
| 500 | 67.19% / 64.06% | 76.56% / 67.19% |
| 1000 | 70.31% / 68.75% | 68.75% / 60.94% |
| 1500 | 68.75% / 59.38% | 64.06% / 59.38% |
| 2000 | 59.38% / 65.62% | 67.19% / 57.81% |

## Interpretation

Full-prefix reconstruction corrects the measured recurrent-state mismatch and
produces a useful middle-distance known-goal gain in this screen. It does not
solve overall navigation or the degradation with continued imitation updates.
Exploration is below the starting checkpoint, especially on longer routes.
Do not promote this checkpoint as a general navigation replacement.

This changes the historical context supplied to the recurrent state, while
backpropagation still covers only 16 steps. It does not test longer-horizon
credit assignment through memory. Collection is capped at 512 steps while
validation allows 1024; behavior beyond collection history remains another
limitation. Pure learner data and balanced losses are fixed across both arms;
subsequent states differ as their policies diverge, as expected in DAgger.

The next useful comparison would retain correct full-history reconstruction
and independently vary the gradient window, or test whether new-goal gains
can be retained without losing exploration. Neither has been run here. Both
training arms, held-out evaluations, preflight checks, and reporting are complete.
No further training or PPO job is queued.
