# Decision-budget and policy-update repair

## V0 provenance

`artifacts/foundation-general-training-v4/champions/V0.pt` was initialized from
scratch, then behaviorally cloned for 10 epochs from 5,674 scripted decisions.
It is not an inherited berserk/scenario model. Training seeds ended in:

| Seed suffix | Decisions | Final floor | Final score |
| --- | ---: | --- | ---: |
| 2746 | 224 | D:2 | 9 |
| 2747 | 1,217 | D:3 | 60 |
| 2748 | 233 | D:2 | 14 |
| 2749 | 2,000 | D:4 | censored |
| 2750 | 2,000 | D:3 | censored |

These are bootstrap training games, not the held-out evaluation scores. The
teacher is `teacher.py`: basic exploration/approach/melee/rest/stairs, with a
small healing-consumable check. The neural actor selects its own actions.

## Reproduced update failure

The old model used the same scalar output for policy logits and absolute final
score regression. Fitting selected actions to `log(1 + final_score)` destroyed
relative action preferences and changed the shared navigation representation.
Unchosen action outputs were unconstrained, and no paired action comparison
justified these changes.

`repair_update.py` rebuilds a challenger from V0 using only the existing training
replay (8,552 ordinary transitions), not held-out evaluation trajectories. On a
fixed diagnostic sample of 256 training states:

| Stage | Agreement with V0 | Melee choices | Rest choices |
| --- | ---: | ---: | ---: |
| V0 | 100% | 15 | 60 |
| Anchored BC update | 97.27% | 15 | 59 |
| Old score update applied to that same BC policy | 9.77% | 4 | 2 |
| Independent critic update instead | 97.27% | 15 | 59 |

The independent critic leaves every actor parameter bitwise unchanged. A small
paired-counterfactual update moved the empirical preferred-action margin from
-24.86 to -22.69; it did not flip that ordering. This proves a learning direction,
not optimal action selection or stronger play. Artifacts and diagnostic-only
legacy checkpoint are in `artifacts/update-repair-v2/`.

## Cutoffs and rejected actions

The previous fifth V0 evaluation included 550 rejected boomerang throws while
held in a net. Source inspection confirmed throwing is forbidden while caught.
The interface now excludes those throws (and throws while berserk). An action
rejected without spending a turn is suppressed until the next game turn; that
mask is included in Crawl's embedded Lua save state.

Default episode budget is now 2,000 decisions **per distinct branch/floor**, with
cumulative counts on revisits; global emergency cap is 100,000. Sixteen decisions
with no game-time advancement produce an explicit adapter-stall truncation.
Administrative truncations save checkpoints and remain censored, not synthetic
deaths or zero returns. Results include budget counts, reason and snapshot path.

The new full-game comparison uses the same five evaluation seeds, V0 versus a
repaired update, both on the corrected interface and floor-aware budgets. It is
a regression validation, not a new untouched final test set. See
`artifacts/floor-budget-v0-validation/results.json` and
`artifacts/floor-budget-repaired-validation/results.json`.

All ten games completed in death with actual final scores, no cutoffs or errors:

| Evaluation seed suffix | V0 score / floor | Repaired score / floor |
| --- | --- | --- |
| 000 | 46 / D:2 | 37 / D:4 |
| 001 | 77 / D:2 | 135 / D:4 |
| 002 | 58 / D:3 | 45 / D:3 |
| 003 | 25 / D:3 | 41 / D:3 |
| 004 | 102 / D:3 | 84 / D:3 |

Mean scores are 61.6 versus 68.4 (+11.0%). The paired mean difference is +6.8,
but the bootstrap lower confidence bound is -14.2. **No promotion**: five pairs
do not establish reliable score superiority. V0 remains the champion. The
repaired update no longer exhibits the old five-game navigation collapse.
The formerly truncated V0 seed 004 now finishes in 1,460 decisions after the
illegal-throw fix, so that particular run did not need a larger budget.

The small autonomous run `artifacts/update-floor-smoke-v2` completed one
collect/train/counterfactual/evaluate cycle with no recorded failures, and
`artifacts/determinism-budget-v2` passed real-engine save/replay determinism.
All 24 automated tests pass, including collector-level floor accounting,
old-checkpoint policy preservation, independent-critic isolation, paired
preference direction, disk safety, and real-engine rejection-mask save/restore.
