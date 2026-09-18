# First symbolic GRU PPO run

This is actual on-policy recurrent PPO, initialized from the 12,000-update
supervised/DAgger symbolic GRU checkpoint. It tests whether reinforcement
learning preserves or improves navigation without teacher labels or an
imitation anchor. It is not a from-scratch learning test.

## Configuration

- Seed 0; target 1M **active decisions**, saving at the first complete episode
  wave beyond 100k, 500k, and 1M. Overshoot is reported.
- Existing synthetic 32x32 train/validation/test/long layouts. Three training
  task groups sampled equally: known stairs, exploration, threat backtracking.
  No ordinary full-size Crawl floor training in this run.
- 128 parallel environments; synchronous complete episode waves; 256 physical
  turn deadline. Finished slots remain inactive until the next wave.
- Rewards: exit +1, death -1, timeout 0. No exploration, kill, or turn reward.
- Gamma .999 **per decision**, GAE lambda .95, clip .2, entropy coefficient .001,
  squared value loss coefficient .25, Adam 1e-5, gradient clip .5, four epochs.
  Stop remaining updates in a wave if a minibatch's approximate KL exceeds .02.
- All layers trainable, including the previously untrained value head. No value
  warmup, teacher regularization, frozen encoder, or reward shaping. This is a
  first diagnostic, not a claim these settings are optimal.
- Sequences preserve 16 consecutive decisions and start from the detached
  hidden state recorded during collection. This is standard truncated recurrent
  PPO: initial states become stale as parameters change within PPO epochs;
  there is no burn-in or full-episode recomputation in this version.
- Entirely inactive sequences are removed. Partial terminal suffixes and dummy
  minibatch padding are excluded from loss and advantage normalization.

## Execution and validation

Uses optimized channels-last CNNs, the identity-pool bypass, compiled encoder
and heads, mixed precision, cuDNN sequence training, and graphed inference.
Training forward/backward is not CUDA-graph captured. Raw symbolic preprocessing
is stored once per observation as floating-point inputs; CNN features are
recomputed with gradients every update. It receives no frontier route hint.

Checks before each wave's updates compare stored action log-probabilities with
sequence replay. A smoke run passed with maximum log-probability difference
.0031 or less (mixed precision GRUCell versus cuDNN sequence rounding). All
parameter gradients were present and finite. Independent checks verify terminal
GAE, masking of padded states, and per-environment chronological sequence order.

Baseline and checkpoint evaluation use fixed held-out scenarios, greedy main
and long evaluation, and sampled main evaluation. Evaluation preserves training
RNG state. Training time includes collection, preprocessing, packing, updates,
and compilation startup, but excludes evaluation and checkpoint serialization.
Reports separately record collection/update time, active-slot fraction, KL,
replay discrepancy, and real active decisions/s. Do not compare this directly
with the 58k network-only estimate: that assumed full useful batches and omitted
simulation, preprocessing storage, sequence assembly, and padding overhead.

## Commands and outputs

Use the compiler-header `CPATH` described in EXECUTION-OPTIMIZATION.md.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_symbolic_ppo.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/symbolic_ppo.py --smoke --name unique-smoke-name
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/symbolic_ppo.py
```

The runner refuses to overwrite an existing checkpoint and locks its output
directory. It writes bounded checkpoints (latest plus three milestones), no
rollout datasets. Live manifest, progress, and checkpoints are in ignored
`learning-runs/remembered-grid/symbolic-ppo-seed0/`; log is the adjacent
`symbolic-ppo-seed0.log`. Final report is `results/symbolic-ppo-seed0.json`.

## Completed seed-0 result

The run completed 1,005,735 active decisions in **112.25 training seconds**,
including compilation startup and excluding evaluation/checkpoint writes:
**8,960 active decisions/s**. This is a measured end-to-end training loop for
these fixtures, not the full-size network-only estimate. Rollout/replay maximum
log-probability discrepancy remained below .00575, all gradients were finite
and present, and the .02 KL early-stop threshold was never reached.

| Greedy held-out success | Starting checkpoint | 103,030 | 507,121 | 1,005,735 |
|---|---:|---:|---:|---:|
| Main known stairs | 91.80% | 92.97% | 83.20% | 58.59% |
| Main exploration | 94.53% | 93.36% | 92.97% | 85.55% |
| Long known stairs | 77.34% | 81.25% | 54.69% | 34.38% |
| Long exploration | 81.25% | 82.03% | 80.47% | 71.88% |
| Main/long threat backtrack | 100% | 100% | 100% | 100% |

Main known-stair and exploration sets contain 256 episodes each; long sets
contain 128 each. Threat sets contain 32 each. No held-out deaths occurred;
all failures are timeouts. Main known-stair mean turns rose from 56.84 to
119.51, and long known-stair mean turns from 157.19 to 330.49, including failures.

Sampled main known-stair success changed 82.42% -> 90.62% -> 78.52% -> 63.28%;
sampled exploration changed 92.58% -> 93.75% -> 97.66% -> 94.92%. Therefore the
known-goal decline is not just greedy decoding. Validation also degraded
(known stairs 89.84% -> 54.69%, exploration 87.50% -> 75.78%).

**Conclusion:** the optimized recurrent PPO pipeline runs quickly, but this
unanchored all-layer fine-tune does not improve the original navigation policy
reliably and loses substantial competence by 1M. The early checkpoint is a
mixed small change, not established improvement from one seed. Small individual
PPO KL values did not prevent cumulative degradation. The checks rule out the
specific sequence/terminal/gradient failures tested, not every implementation
or algorithmic issue. This run does not isolate sparse rewards, shared-critic
interference, or stale recurrent states as the cause; those remain hypotheses.
Original and milestone checkpoints are retained.

[Raw final report](../../results/symbolic-ppo-seed0.json).
