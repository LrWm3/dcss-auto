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

## Original streaming PPO: prevention through 1M decisions

Same seed, source imitation weights, rewards, 512x64 rollout/GAE and 1024 final
validation placements as the historical tiny-turn-cost control. Changed only the
listed intervention. Each condition reached 1,000,448 decisions.

| Condition | Sampled clears | Greedy clears | Sampled clear-only turns |
|---|---:|---:|---:|
| Initial imitation | 992/1024 (96.88%) | 967/1024 (94.43%) | 680.28 |
| Existing unchanged PPO control | 975/1024 (95.21%) | 351/1024 (34.28%) | 707.77 |
| Freeze first affine encoder layer | 997/1024 (97.36%) | 967/1024 (94.43%) | 678.84 |
| All layers train, learning rate .00003 instead of .0003 | 995/1024 (97.17%) | 962/1024 (93.95%) | 680.91 |
| Drop negative MOVE actor terms | 84/1024 (8.20%) | 4/1024 (.39%) | 861.30 |

The frozen layer was verified bit-identical to initialization. Other parameters
changed, including second encoder layer L2 displacement 1.385 (versus 1.172 in
control), so preservation did not simply freeze the whole model. First-layer
L2 displacement at 1M: control 2.946, lower LR .316, frozen 0. Actor-only first
update first-layer weight displacement was .528 versus original norm 22.307;
bias displacement .0267 versus original norm .1419.

These independently support excessive actor-driven first-layer representation
changes as a cause of degradation. The negative-credit ablation is a causal probe
of the first update, not a viable general training objective: it fails badly over
longer training, predominantly by death. Preservation through 1M is not evidence
of guaranteed long-run stability or significant improvement beyond imitation.

## Cross-check: repair independent degraded checkpoints without training

Use saved 1M policies, retain every trained parameter except replacing body.0
weights/bias with the original imitation layer. Same 128-case validation panel,
original reward/native evaluation environment (physics unchanged across reward
variants). No optimization, new demonstrations or action overrides:

| Source policy | Sampled clears before -> after graft | Greedy clears before -> after graft |
|---|---:|---:|
| Original tiny-turn-cost 1M | 125 -> 122 | 48 -> 122 |
| Small kill-reward 1M | 122 -> 125 | 34 -> 122 |
| Full-episode-return ~1M | 115 -> 122 | 0 -> 120 |

These are 128-case diagnostics and must not be confused with prior 1024-case
final percentages. The graft recovers the greedy behavior across all three
training variants; it is not uniformly an improvement to sampled performance.
This strengthens the mechanism beyond the isolated first update. It does not
claim every remaining death or all longer-run deterioration has the same cause.

The fixed-state loop probe captures both endpoints in eight cases after the
first actor-only update. Example, episode 83: at (54,44), known-frontier route
points SE. Original MOVE probabilities give SE .999; after update SE falls to
.111 and W rises to .408 (largest), so greedy moves to (53,44). There the updated
policy assigns E .916 and returns to (54,44). Restoring just body.0 restores
SE .998 at the first endpoint, breaking the cycle. Identical observations and
action masks are passed to each policy; this is a changed map-to-direction
computation, not changed simulator geometry or frontier selection.

## Additional control and conclusion

Omitting advantage-mean subtraction preserved the first isolated update but
failed in streaming training: at 1M both sampled and greedy clears were zero
(sampled deaths/timeouts 30/994; greedy 19/1005). Thus centering is not itself
the general root cause or a simple switch to disable permanently. Likewise
negative-MOVE gradient suppression was an explanatory intervention, not a fix.

The experimentally established mechanism is actor-driven destruction of the
pretrained first-layer navigation representation under our PPO update settings.
Negative navigation advantages drive the reproduced first damaging step; shared
first-layer changes carry its behavioral effect. Critic-only training does not
reproduce that step; detaching the critic does not prevent it. First-layer grafts
reproduce AND reverse the damage. Freezing this layer or lowering the learning
rate tenfold prevents the large loss of competence through 1M in the original
streaming setup, while other policy/value parameters still train.

This identifies a concrete representation/optimization failure, not a discovered
indexing bug or proof that sparse reward is adequate for all learning. Standard
PPO clipping constrains sampled action-ratio terms, not all first-layer feature
changes or downstream greedy trajectories. Preserving competence is established
here; reliable improvement past imitation and long-run stability are not. A
reasonable next baseline is the lower learning rate, with the frozen-layer model
as a control. No additional training was launched beyond these diagnostics.

Primary artifacts: results/autoregressive-update-{cause,trace,credit-intervention,
prevention,parameter-drift,loop-probe,repair}.json and
results/autoregressive-no-centering.json. Prevention screen training times were
23.65s (frozen layer), 25.39s (lower LR), 25.72s (drop negative MOVE); total screen
wall time 272.79s including all evaluations. No-centering wall time 88.87s.

## Authorized continuation to 10M

Continue the lower-LR policy first, then the frozen-first-layer control, each from
its existing 1,000,448-decision checkpoint. Preserve model, optimizer, simulator,
RNG, training counters/history and original reward/PPO settings. Only the stopping
budget, evaluation milestones and source timing metadata change. Evaluate sampled
and greedy on 1024 placements at 5,000,192 and 10,000,384 decisions. No fresh
imitation or additional reward changes. Check first-layer bit equality against
original imitation at both frozen-condition milestones. Report cumulative and
additional training time separately.

Launcher: diagnostics/autoregressive-imitation/continue_prevention_10m.py. Separate
suite learning-runs/autoregressive-update-prevention-10m keeps original 1M artifacts
intact; 2 GiB cap and 10 GiB reserve. Source checkpoint and script hashes recorded.
Incremental summary: results/autoregressive-update-prevention-10m.json. Suite status
records active condition, completion or failure. This tests whether the 1M rescue
persists, merely delays damage, or enables improvement. Existing original-rate
10M control ended with zero sampled and greedy clears.
