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
