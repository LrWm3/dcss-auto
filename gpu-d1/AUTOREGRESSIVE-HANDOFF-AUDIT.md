# Early PPO handoff audit

Replay from preserved controller-imitation checkpoint. First test the frozen
policy on the actual training distribution (512 worlds, 256 maps, clumped
placement), then isolate 30 PPO updates per condition: normal, no entropy,
value loss only, policy loss only. Each update uses 512 worlds x 64 decisions,
four optimizer epochs, and original optimizer/GAE settings. Each condition resets
model, optimizer, environment and RNG; sampled evaluations preserve training RNG.

A fixed 128-placement diagnostic panel spans 32 validation layouts. Evaluate
before training and after updates 1, 2, 4, 8, 16, 24 and 30. These are diagnostic
comparisons, not full-panel final-policy selection. Log training episode outcomes,
values, advantages, losses, gradient norms, policy KL and probability changes.
Check stored versus recomputed pre-update log probabilities, legal actions,
clear-only reward aggregation, terminal flags, and physical-turn accounting.

Script: diagnostics/autoregressive-imitation/handoff_audit.py. Raw results:
results/autoregressive-handoff-audit.json. No changes to production trainers or
original checkpoints. No diagnostic model checkpoints or rollout datasets saved.

## Completed findings

Frozen imitation policy on training distribution: 479/512 clears, 33 deaths,
zero timeouts. Diagnostic baseline: 124/128 clears. Thus useful behavior transfers
to the actual training environment before updates.

| Update components | After update 1 | After update 8 | After update 30 |
|---|---:|---:|---:|
| Normal PPO (policy + value - entropy bonus) | 0/128 | 0/128 | 0/128 |
| PPO without entropy bonus | 124/128 | 122/128 | 122/128 |
| Value only (including shared encoder) | 124/128 | 120/128 | 121/128 |
| Policy loss only | 124/128 | 121/128 | 125/128 |

All variants start with the identical first rollout: zero clear rewards, 21 deaths,
zero predicted values, and zero advantages. Normal PPO's first optimization has
exactly zero policy and value losses. Only entropy regularization supplies a
nonzero gradient. It changes the policy substantially: mean old-to-new KL 0.907,
mean total variation 0.399, post-update entropy 0.755 nats (initial approximately
0.0513). The top action type changes on only 0.44% of rollout states, so looking
only at type choices would miss the substantial directional/distribution change.
Immediately afterward the diagnostic panel has zero clears and 123 timeouts.

Without entropy regularization, the first update leaves behavior unchanged.
The first clear reward arrives during rollout 5. Over 30 updates it receives
1,186 clear rewards and stays at 122-124 diagnostic clears. Normal PPO receives
zero clears throughout. Value-only and policy-only do not reproduce collapse.
These controlled comparisons identify entropy regularization as the cause of the
initial failure in this setup, rather than merely a suspected contributor.

The PPO clipped surrogate does not clip the entropy term. With zero initial
advantages, the clipped policy objective supplies no counterpressure to this
entropy-driven drift. This does not establish that all entropy bonuses are bad:
the issue is this coefficient and optimizer schedule applied to a confident
cloned policy before reward/value feedback becomes available. Omitting the bonus
does not disable sampling or all exploration.

Checks passed: legal sampled actions, raw and training reward equal clear flag
(gamma=1), done equals clear/death/timeout union, completed episode rewards and
physical durations, pre-update stored/recomputed log probabilities (maximum
absolute discrepancy under 4.3e-6). Native transition and rest/deadline tests were
also completed before the original experiment. These checks do not constitute an
exhaustive proof of all trainer behavior.

Each variant used 983,040 decisions; all diagnostics took 255.35 seconds. This
small one-seed panel establishes the failure mechanism and a stable handoff,
not improvement over imitation or which ablation is best. No corrective full-panel
training run was launched in this audit. Original checkpoints remain unchanged.
