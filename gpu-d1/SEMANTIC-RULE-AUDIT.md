# Semantic controller: rule substitutions and reward comparison

Frozen seed-0 10M policy, the same 1,024 validation placements, no retraining.
These are diagnostics on the reused validation panel, not an untouched test set.

All rule ablations retain forced REST whenever its existing mask permits it.
Other substitutions use the existing observation-only deterministic controller:
attack an adjacent enemy; wait for visible awake enemies to approach; or make
progress toward sleepers/frontiers. The combined variant follows the native
controller exactly, including attack-before-rest priority. Full episode outcomes,
kills and physical turns must reproduce the reference for each placement.

Baselines also must exactly reproduce the previous forced-rest evaluation.
Policy sampling uses the same seed and full batch shape. Different actions can
change later states and consume environment randomness differently, so paired
initial placements do not mean identical future combat random draws.

Disagreement logging records the controller's recommended category, model action,
below-half-HP status, visible/adjacent enemy counts, and whether a disagreement
occurred within ten policy decisions of death. The last quantity is descriptive,
not proof that those choices caused the death.

For one-action replays, select the first three reference-only failed greedy
episodes with a disagreement in each category and take their last disagreement
in that category. Cases may overlap in episode identity. Restore the complete
state, observation and action mask; branch only the first action, then follow
the same greedy policy plus forced rest in both branches. Replay the original RNG
state and 16 additional future RNG states per case, paired between alternatives.
The exact original-model branch must reproduce failure. Query the RNG offset
from the actual compiled State definition rather than assume structure layout.
This is a deliberately selected diagnostic suite, not an unbiased effect estimate.

Reward comparison separately accumulates both the undiscounted shaped reward and
physical-turn-discounted return from episode start:

    G = sum_over_macro_decisions(0.99 ** prior_elapsed_turns * macro_discounted_reward)

Each macro's discounted reward already discounts its internal physical turns.
Duration multiplies the subsequent discount factor. Assertions check total ticks
and the final factor against 0.99 ** total_physical_turns. Scores include all
reward terms and terminal rewards, without bootstrapping at the episode deadline.
This measures the discounted task return; PPO additionally uses approximate value
learning, GAE, clipping and entropy regularization, so it is not a claim that PPO
exactly optimizes an initial-state return or that the learned policy is optimal.

Reproducers:
- `diagnostics/semantic-actions/rule_ablation.py`
- `diagnostics/semantic-actions/reward_scores.py`

Run with `gpu-d1/.venv/bin/python`. Local state snapshots and native RNG-offset
helper stay under ignored `learning-runs/semantic-rule-audit`. Compact results
are saved in `results/semantic-actions-rule-ablation.json` and
`results/semantic-actions-reward-scores.json`.

## Rule substitution results

All rows below include forced rest. Counts are out of 1,024 episodes.

| Added rule | Sampled clears/deaths/timeouts | Greedy clears/deaths/timeouts |
|---|---|---|
| None | 972/44/8 | 971/46/7 |
| Adjacent attack | 974/42/8 | 972/45/7 |
| Wait for awake enemy approach | 988/26/10 | 988/25/11 |
| Engage sleepers / explore | 965/52/7 | 971/48/5 |
| Attack + wait for approach | 991/23/10 | 989/24/11 |
| All deterministic rules | 986/27/11 | 986/27/11 |

The sampled rest-only baseline has 34 reference-only clears and 20 model-only
clears; greedy has 35 and 20. Therefore the net gaps (14/15) are not simply sets
of 14/15 uniquely deficient model episodes. Combined rules exactly reproduce the
reference per episode, including kills and turns, in both evaluation modes.

With rest forced, the sampled policy disagrees with adjacent ATTACK only 58 times
out of 146,546 opportunities, and greedy only 12/146,967. In contrast, it chooses
ENGAGE rather than WAIT in 27,824/30,870 sampled and 28,091/32,059 greedy
nonadjacent awake-enemy situations. The latter is the major behavioral difference.
Progress overrides do not improve aggregate results consistently. Combining attack
and waiting gives 991 sampled / 989 greedy clears; the few extra clears over 986
are not evidence of a statistically established advantage.

## Saved-state replay outcomes

Eight selected state/category cases (seven distinct episode IDs) were tested.
Three awake-approach substitutions (ENGAGE → WAIT) rescue all three original
failed continuations. Across 16 fresh future RNG states each, however, the model
choice clears 45/48 and WAIT 46/48. Thus these selected original failures do not
establish a large robust single-action advantage: their particular random futures
matter. The larger full-episode intervention remains the better evidence.

Two last-moment adjacent WAIT → ATTACK substitutions at 2 HP save neither case,
under the original RNG or the additional futures. One sleeper ENGAGE substitution
rescues its original failure (13/16 versus 15/16 under varied futures); another
remains a timeout, and the third remains a death under original randomness with
mixed results under new futures. Zero exploration-category cases met the selected
reference-only greedy-failure criterion.

These are one-action substitutions followed by the original greedy + rest policy.
Failure to rescue is not proof that an episode was unavoidable; earlier actions,
other alternatives or a different continuation could change the outcome.

## Raw reward versus discounted return

| Controller | Clears | Raw reward | Discounted return | Mean turns |
|---|---:|---:|---:|---:|
| deterministic | 986 | 27.3038 | 4.7243 | 681.00 |
| sampled_baseline | 950 | 26.7474 | 6.0873 | 524.25 |
| sampled_rest | 972 | 27.0658 | 5.1235 | 622.18 |
| sampled_rest_wait | 988 | 27.3558 | 4.7231 | 681.27 |
| sampled_rest_attack_wait | 991 | 27.4266 | 4.7375 | 682.87 |
| greedy_baseline | 961 | 26.9920 | 6.1390 | 519.58 |
| greedy_rest | 971 | 27.0937 | 5.1403 | 620.05 |
| greedy_rest_wait | 988 | 27.3685 | 4.7361 | 683.08 |
| greedy_rest_attack_wait | 989 | 27.3982 | 4.7430 | 683.84 |

Raw reward favors the deterministic controller over the unmodified learned policy;
discounted return reverses that ranking. Forcing recovery and waiting improves
clears and raw reward while reducing discounted return. This directly demonstrates
that these survival-improving interventions are worse according to initial-state
return with the training gamma, on this panel. It supports objective mismatch as
an explanation for the policy's aggression, but does not prove the exact learning
mechanism or establish optimality of the learned policy.

At gamma=0.99, a reward 100 physical turns later has weight about 0.366, and at
500 turns about 0.00657. The task lasts roughly 500–680 turns on average here.
The same per-turn rule applies to both REST and EXPLORE; this is not an asymmetric
macro implementation. They differ in immediate reward and their delayed benefits.

All score-run clear/death/timeout/turn metrics match their rule-ablation counterparts.
Raw reward is accumulated in float64 here, so tiny rounding differences from the
previous float32 reports are expected. Both diagnostics completed successfully.
