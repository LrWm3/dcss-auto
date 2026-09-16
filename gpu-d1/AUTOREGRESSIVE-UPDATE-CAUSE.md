# Causal investigation of PPO navigation damage

The user requested a concrete cause, not another reward sweep. We reproduced the
first damaging update from the complete-episode GAE control exactly, then replayed
its fixed data with surgical gradient and weight interventions. We also tested
prevention in the original streaming PPO setup. No teacher loss was added.

## Fixed-batch reproduction

Original competent imitation, seed 0, 64 training episodes, 33,733 valid decisions,
55 clears/9 deaths. Same rewards (+1 clear, -.00001 per physical turn), normalized
GAE(.95) cut at 64, same four PPO epochs/minibatches/Adam, fixed minibatch RNG.
All one-update evaluations use 128 held-out placements (baseline 124 sampled,
120 greedy). They are diagnostics, not the 1024-placement final training panel.

| Intervention on identical batch | Sampled clears | Greedy clears |
|---|---:|---:|
| Full actor + critic update | 125 | 6 |
| Actor update only | 124 | 6 |
| Critic update only (shared encoder allowed to change) | 122 | 121 |
| Critic head only | 124 | 120 |
| Actor update, shared encoder frozen | 124 | 119 |
| Actor + critic, critic detached from encoder | 124 | 6 |
| Actor update, learning rate /10 | 124 | 120 |

Thus actor gradients suffice for this collapse; critic interference is not its
necessary cause. The effect is not just incorrect critic-head weights at inference.

## Which weights carry the damage?

Take weights from the actor-only update, transplant specified subsets into the
original policy, and evaluate with no further training:

| Updated weights transplanted | Sampled clears | Greedy clears |
|---|---:|---:|
| Entire encoder (body) | 123 | 4 |
| Heads/embedding, original encoder | 124 | 120 |
| First encoder affine layer only | 125 | 5 |
| Second encoder affine layer only | 124 | 120 |

This localizes sufficient damage to body.0 (first Linear layer, weights and bias).
It is not a direction-index conversion or blocked-movement failure. The same
fixed observations are evaluated by unchanged downstream layers after a graft.

## Which actor gradient drives it?

Of 21,243 MOVE samples, 97.05% were in episodes that cleared and their mean sampled
action probability before training was 99.47%. Only 4.20% had positive normalized
advantage. Successful-episode membership does not prove every move was useful;
it shows how little the final success protects early navigation in this estimator.

| Actor terms retained | Sampled clears | Greedy clears |
|---|---:|---:|
| Only negatively credited MOVE samples | 0 | 0 |
| Only positively credited MOVE samples | 122 | 120 |
| Only non-MOVE samples | 123 | 121 |
| All except negatively credited MOVE samples | 123 | 121 |
| All samples, divide by std but omit batch-mean subtraction | 124 | 119 |
| All samples, shuffled normalized advantages | 121 | 80 |

Subset masks retain the original minibatch denominator, minibatch order, optimizer
and epochs. Removing negative terms is a diagnostic intervention, not an unbiased
replacement policy-gradient estimator or a recommended permanent algorithm.

Concrete chain in this batch: temporal/critic-based credit plus batch centering
labels almost all established navigation choices negatively; actor updates push
down those choices and rewrite the first learned feature layer; this changes
navigation direction rankings and creates greedy movement cycles. PPO clipping
of sampled action ratios does not prevent this measured behavior. The critic is
initially zero here. A negative advantage means below the estimator's baseline,
not that the sampled move actually caused failure. Complete-return training later
also deteriorated, so short GAE truncation is not the only way this interaction
can arise, and these results do not prove all negative movement credit is wrong.

## Reproduction and artifacts

Run scripts in diagnostics/autoregressive-imitation using the GPU venv:
`update_cause.py`, then `update_trace.py`, then `update_credit_intervention.py`.
The trace script saves compact intervention weights under ignored
learning-runs/autoregressive-update-cause; no trajectory datasets are written.
`update_loop_probe.py` captures both endpoints of induced loops for fixed-state
before/after/restored-layer distributions. `update_repair.py` grafts the initial
first layer onto independently trained degraded 1M checkpoints.

`update_prevention.py` runs original streaming PPO (512x64) to 1M with a frozen
first layer, learning rate /10, or negative-MOVE actor-gradient removal, using
same source weights and rewards. `update_no_center.py` queues a no-centering
condition afterward. Diagnostic flags default off in the shared runner. Existing
control remains results/autoregressive-turn-cost.json. Full validation is 1024
placements, with zero/500K/1M evaluations; disk cap 2 GiB and 10 GiB reserve.
No improvement claim should be inferred merely from preserving imitation; compare
clear rate, successful-clear turns and original objective. One training seed.
