# Navigation collapse and conservative handoff checks

Navigation replay uses the full original 1,024 validation placements at imitation,
500K and 1M checkpoints. Compare original type-first greedy with joint-action
argmax. Count immediate MOVE reversals and streaks of at least eight reversals
(two-square oscillations). Compare repeated-square observations excluding only
time. Original greedy episode outcomes are asserted against saved results.

| Checkpoint | Greedy mode | Clears | Timeouts | Timeout episodes with oscillations | Reversals / movement decisions |
|---|---|---:|---:|---:|---:|
| Imitation | type / joint | 967 | 25 | 25 | 12.8% |
| 500K | type | 17 | 982 | 942 | 90.5% |
| 500K | joint | 17 | 981 | 937 | 90.6% |
| 1M | type | 78 | 918 | 900 | 87.4% |
| 1M | joint | 81 | 915 | 898 | 87.3% |

At 500K, 1,732,082 of 1,734,132 immediate reversals return to observations identical
except time. No MOVE attempts are stationary/blocked in these rollouts. Thus the
failure is overwhelmingly oscillatory movement, not WAIT selection, wall bumps,
or the distinction between the two greedy definitions. Counts establish the
presence of loops, not a counterfactual proof every timeout is caused by them.

## Representation

The feedforward model sees current coordinates, elapsed turns/2048, floor tiles
seen/1024, locally remembered terrain, visible enemies/sleep status, and frontier
location/distance/route cue. Remembered terrain distinguishes seen from unseen;
it is not a record of player visits. There is no previous-action input, player
visit count, recent-position history or recurrent state. Repeated observations
therefore cannot directly identify a previous traversal. Nevertheless imitation
already achieves 94.4% greedy clears with these inputs, so lack of history alone
does not explain why PPO destroys useful behavior. Clear-only reward also makes
extra turns free unless they change eventual success within the deadline.

## Conservative diagnostic design

Three 30-update conditions (983,040 decisions each): KL restriction only, fitted
critic only, and both. Entropy remains disabled. Existing no-entropy run is the
reference. Fit only the linear critic head to terminal success labels from 512
frozen-imitation episodes on training maps; actor and shared encoder weights must
remain bit-identical. Use episodes 0..383 for fitting and 384..511 for held-out
value error (state-weighted); these are all training-distribution maps. Eight
critic fitting passes, Adam .001. No demonstration or reward change.

KL restriction checks exact categorical old-policy-to-new-policy KL averaged over
the full collected rollout after every optimizer epoch. Reject/roll back any
epoch exceeding .01, restoring model and optimizer state, and stop that update.
This is a diagnostic conservative limiter, not a claim of globally bounding policy
changes on unseen states. Report accepted/rejected epochs so freezing learning
cannot be mistaken for improvement. All other PPO settings remain unchanged.
Evaluate sampled and greedy on the fixed 128-placement diagnostic panel. This
small one-seed panel assesses mechanism, not full-validation superiority.

Scripts: diagnostics/autoregressive-imitation/navigation_audit.py and
conservative_audit.py. Results: results/autoregressive-navigation-audit.json and
results/autoregressive-conservative-audit.json. Original checkpoints unchanged.

## Conservative diagnostic results

Each condition completed 30 updates (983,040 decisions), with entropy disabled.
Fixed diagnostic panel: 128 placements. Starting imitation: 124 sampled clears,
120 greedy clears.

| Condition | Final sampled clears | Final greedy clears | Accepted optimizer epochs | Rejected epochs |
|---|---:|---:|---:|---:|
| KL restriction only | 124 | 58 | 93 | 12 |
| Critic fitting only | 95 | 0 | 120 | 0 |
| Critic fitting + KL restriction | 122 | 0 | 79 | 15 |

The KL check held: maximum accepted post-update full-rollout KL was .009879
(KL only) and .009985 (combined). Greedy deterioration is therefore not explained
solely by a single unconstrained update; small per-update changes can accumulate
and can alter a deterministic directional choice. This is not a cumulative bound
against the original imitation policy, nor a bound at every individual state.

Critic fitting used 279,340 states from 512 training-map episodes, 472 of which
cleared. Held-out state-weighted MSE improved from .97926 to .02042. However,
always predicting success would already have MSE .02074 on these states: this
fit is mainly learning a strong success prior, not demonstrably accurate local
advantages. All actor and shared-encoder tensors were verified unchanged by
fitting. Fitting this linear critic does not improve the handoff here; the result
does not rule out better value fitting with a richer critic or different targets.

The combined test preserves sampled performance but not greedy navigation. The
critic-only test eventually also hurts sampled clears (95/128). None establishes
an improvement over imitation. Protocol duration: 338.24 seconds, including both
sampled and greedy checks. All original checkpoints remain unchanged.

Implication: temporal visit/action information would make repeated traversal
observable, while the present clear-only objective gives no independent incentive
to avoid it when sampling still clears. Those are separate representation and
objective questions. A reference-policy or navigation imitation constraint would
instead directly test preservation of the already learned navigation behavior.
No new representation, reward, or further training run was introduced here.
