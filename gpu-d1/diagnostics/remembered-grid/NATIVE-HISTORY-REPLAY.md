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

Collect 32 environments, at most 512 steps, refreshing learner data every100
updates and expert data every500. The policy memory resets only at episode
reset. Both history variants preserve the original raw chunk order, balanced
sampling, losses, and RNG calls. On-policy trajectories diverge as weights do;
this is update-budget matched, not identical-data or wall-time matched.

Evaluate every500 updates with a1024-turn deadline. Select the trained checkpoint
by mean middle-band validation success (64 cases per category), then test on
middle-band and original longer-route held-out cases (128 per category, on32
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

Preflight passed: 5,965 collected decisions, all383 retained chunks match the
legacy buffer exactly, and sampled short-history losses both equal1.6907693.
Full-history replay agreed on all136 checked actions before and after one
optimizer update; maximum per-state KL was1.09e-5 and2.12e-5 nats respectively.
Encoder gradients and recurrent weight changes were verified. Prefix states
have no gradient. Initial checks exposed a hidden-state shape mismatch during
review and a CUDA illegal access in the large multi-input stack path; history
assembly now uses16-frame stacks followed by concatenation. Training was gated
on the successful corrected checks.
