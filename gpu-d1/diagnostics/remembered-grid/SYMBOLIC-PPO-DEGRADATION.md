# Why the first symbolic PPO fine-tune degraded

## Causal controls

All runs start from the same supervised symbolic GRU checkpoint, use seed 0,
the same training scenarios/rewards/optimizer settings, and run to approximately
500k active decisions. Policies collect their own on-policy data, so trajectories
and update counts diverge after the intervention. Comparisons are single-seed
mechanism tests, not independent-seed confidence intervals.

The original joint PPO run supplies the 507,121-decision control. New controls:

- `critic_only`: multiply policy-gradient and entropy losses by zero; train the
  shared encoders, GRU, and value head from the value loss. The policy output
  head must remain exactly unchanged.
- `detached_critic`: apply the value head to `z.detach()`. It still learns and
  supplies GAE values, but its loss cannot change the encoders or GRU. Actor
  gradients can still change those shared features. Combined gradient clipping
  is retained, so this is not a perfectly isolated advantage-estimation control.
- `actor_only`: multiply value loss by zero. The source value head is initialized
  to exactly zero and was never trained by imitation, so it stays zero. This
  retains clipped policy learning, entropy, and the original GAE lambda .95.
- Repeat joint, detached-critic, and actor-only configurations with lambda 1.
  Episodes are complete, making targets actual discounted episode returns,
  without bootstrapping through intermediate value predictions. Gamma stays
  .999. This changes advantage/critic targets, not rewards or architecture.

The critic-only run demonstrates sufficiency, not that joint PPO will degrade
at the same rate without actor gradients opposing the value updates. Detaching
only the critic provides the more direct intervention on ordinary PPO.

## Additional checks

`symbolic_ppo_audit.py` verifies parameter changes by component, evaluates the
original PPO checkpoint using ordinary eager inference, swaps its policy head
with the source head in both directions, and compares loss gradients on the
same collected observations/advantages. It also examines initial GAE versus
complete-return targets on identically sampled trajectories.

Sequence order and terminal GAE checks remain in `check_symbolic_ppo.py`. A new
check verifies lambda=1 targets are independent of arbitrary value predictions
on active episode steps. Before-update rollout/replay checks remain enabled in
every training run. These tests do not establish that every recurrent PPO
implementation choice is optimal.

## AMP overflow handling

The first actor-only attempt stopped at wave 53 after 353,655 completed decisions
because the finite-gradient assertion rejected an AMP overflow before GradScaler
could handle it. Original joint PPO and completed critic-only/detached controls
had not hit this assertion. This cannot explain their observed degradation.

The runner now checks loss finiteness, detects nonfinite unscaled gradients,
lets GradScaler skip Adam and reduce its scale, and records `overflow_skips`.
It then retries on a subsequent minibatch. The actor-only control was repeated
from the same source/seed as `actor_only_retry`, not resumed with missing RNG
state. Its completed run encountered one skipped update. The aborted report is
retained with its reason; it is not treated as a completed 500k result.

## Artifacts

Training controls: `symbolic_ppo_cause_suite.py` and
`symbolic_ppo_return_suite.py`; source runner `symbolic_ppo.py` accepts `--mode`
and `--gae-lambda`. Use distinct output names to avoid overwriting checkpoints.
The scripts stop on errors; the return suite waits for the completed retry
report. Reports are `results/symbolic-ppo-cause-*.json`; checkpoints and logs
remain under ignored `learning-runs/remembered-grid/`.

## Results: identified causes

The evidence identifies **shared-critic representation damage**, compounded by
**inaccurate bootstrapped advantage estimates from a cold critic**. This is not
merely a statement that PPO sometimes forgets. Removing loss components,
changing advantage targets, and swapping checkpoint components causally change
the failure. It does not prove these are the only possible contributors.

| Configuration (~500k decisions) | Main known stairs | Main exploration | Long known stairs | Long exploration |
|---|---:|---:|---:|---:|
| Source, before PPO | 91.80% | 94.53% | 77.34% | 81.25% |
| Original shared critic, lambda .95 | 83.20% | 92.97% | 54.69% | 80.47% |
| Critic only, lambda .95 | 7.81% | 15.62% | 2.34% | 7.03% |
| Detached critic, lambda .95 | 86.33% | 96.48% | 70.31% | 87.50% |
| Actor only, zero value, lambda .95 | 95.31% | 93.36% | 84.38% | 82.81% |
| Shared critic, complete returns | 68.75% | 82.03% | 42.97% | 68.75% |
| **Detached critic, complete returns** | **95.31%** | **92.97%** | **89.06%** | **85.16%** |
| Actor only, zero value, complete returns | 94.92% | 92.97% | 85.94% | 83.59% |

Counts: main groups 256 episodes each, long groups 128. Exact decision counts
are in raw reports. Small differences between the successful controls should
not be ranked confidently from this seed. Main exploration is still slightly
below the source with complete returns; this is not universal improvement.
Detached complete-return greedy threat tests remain 100%, but its sampled main
threat success is 31/32 versus source 32/32. This is a promising correction,
not an established uniformly superior policy.

### 1. Damage is upstream of the action head

Critic-only training changes policy-head parameters by exactly zero, yet
collapses known-stair success. At 500k, L2 parameter changes include GRU 1.0504,
local encoder .7379, global encoder .6269, while policy head change is 0.0.

The original joint PPO **1M** checkpoint was also evaluated with eager inference
and crossed with the source parameters:

| Encoders/GRU | Action head | Main known-stair success |
|---|---|---:|
| Source | Source | 91.80% |
| PPO 1M | PPO 1M | 58.98% |
| PPO 1M | Source | 58.98% |
| Source | PPO 1M | 91.41% |

Thus replacing the action head cannot repair the loss, whereas restoring the
representation almost does. Eager inference also retains the collapse; compiled
inference's original result was 58.59%, a one-episode difference. CUDA graphs or
compilation are not a sufficient explanation for the large loss.

Value and policy losses share the encoders and recurrent state. Predicting a
return is a different objective from retaining the action distinctions learned
by imitation. PPO ratio clipping applies to the policy objective; it does not
directly constrain the value loss's changes to those features. Small per-update
KL does not guarantee small cumulative functional drift.

This is **not** evidence that value gradients always have larger norm or oppose
actor gradients. In the same-data 100k audit, GRU actor-gradient norm was .3656
versus value-gradient norm .01363, cosine .0378; value-head gradient norm was
.5167. The claim of interference comes from the behavioral interventions, not
an unsupported claim of universally opposing or dominant gradients. Adam and
repeated updates further prevent interpreting one raw norm ratio as causal
importance.

### 2. The critic is too inaccurate to provide these bootstrap targets

On a fixed fresh batch collected by the original 100k checkpoint:

- Mean predicted value: **.1015**; mean actual discounted episode return: **.8611**.
- Value MSE to actual returns: **.6699**; explained variance: **-.0102**.
- Mean lambda-.95 target: **.3875**; target MSE to full returns: **.3155**.
- Normalized advantage signs differ for **43.15%** of active decisions between
  lambda .95 and complete returns, on identical trajectories.

The source value head is zero, not pretrained by imitation. With that head,
GAE credit for a terminal success is proportional to `(gamma * lambda)^k`.
At lambda .95, early successful-route steps therefore receive very little
credit unless the critic supplies accurate intermediate values. A paired
initial rollout had 6,137 successful-episode decisions: **53.25%** received a
negative normalized advantage with lambda .95, versus 0% with complete returns.
The minimum success target was .00000221 versus .77949. The trajectories were
the same; only the estimator changed.

Negative advantages on a winning episode are not inherently wrong: some actions
may be inferior or unnecessary. These sign counts alone are not a proof of a
bug. Combined with the inaccurate value predictions and the detached-critic
return intervention (long known stairs 70.31% -> 89.06%), they show why trusting
this cold bootstrap is harmful here. Shared-critic complete returns still fail,
so changing lambda alone is insufficient. Conversely actor-only lambda .95
works reasonably well, so lambda .95 alone is not inherently fatal.

## Practical consequence

Do not immediately train an uninitialized shared critic through the pretrained
navigation representation. For this complete-episode fixture, the tested
correction is **detach critic features and use complete discounted returns**.
All navigation layers remain trainable by actor gradients; freezing the whole
policy or copying the teacher forever is not required by these results.

A separate critic encoder/GRU, trained or warmed on actual returns, is a sensible
next design but was not tested here. Merely detaching a weak linear value head
while continuing to trust its bootstrapped estimates was only a partial fix.
Longer runs and additional seeds are needed before claiming durable improvement.
Stored recurrent-state staleness remains an implementation limitation, but
controls that retain it perform well; it is not necessary to change it to avoid
this observed 500k collapse.

[Checkpoint/gradient/value audit](../../results/symbolic-ppo-cause-audit.json).
