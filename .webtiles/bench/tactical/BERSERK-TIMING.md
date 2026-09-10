# Outcome-trained berserk timing — 2026-09-10

Run: `artifacts/berserk-timing-v1`. Pursuit movement, attacks and recovery waits
remain deterministic. Only the berserk timing rule is learned. No production
deployment or test-set use. This is an outcome-trained contextual rule chooser,
not per-turn unconstrained RL and not another imitation fit.

## Results

Training comprises 12 encounter families on 12 seeds, six RNG offsets each.
Every rule replays every variant from the same initial checkpoint and RNG offset.

| Policy | Recovered | Died | Budget exhausted |
| --- | ---: | ---: | ---: |
| Never berserk | 52 | 11 | 9 |
| Berserk on contact | 67 | 2 | 3 |
| Berserk within two tiles | 68 | 2 | 2 |
| Contact and HP <=70% | 60 | 5 | 7 |
| Learned, leave-one-seed-out | 60 | 8 | 4 |
| Learned, evaluated on its fitting data | 70 | 1 | 1 |

The learned chooser improves on never berserking, but does NOT beat the simple
early timing rules under cross-fitting. Its 70/72 in-sample result is not a
generalization result. Eight validation variants (four encounters, one previously
studied seed) recover under all four rules and the frozen chooser. Validation is
therefore a regression check with a ceiling, not evidence of tactical superiority.

Post-run diagnostic: choosing the best single constant rule using only the other
11 seeds in each cross-fit fold achieves 67 recovered / 3 died / 2 budgets
(near on 66 variants, contact on six). Thus the chooser also loses to a constant
rule selected without the held-out seed's labels, not just the best aggregate rule.

Compared with never, contact rescues 18 previously unsuccessful variants and
loses three previously recovered variants. Near rescues 19 and loses those same
three. Late rescues 12 and loses four. These are paired outcomes across RNG
variants, not independent seed-level wins.

The early-rule regressions are seed 83019004 offset 5 (death instead of recovery)
and seed 83019002 offsets 2/4 (budget instead of recovery). At the end of near's
two budget cases, HP is respectively 58/61 and 61/61, no visible enemies, no
reported status. They are not deaths: one still needs healing, the other has not
completed recovery's quiet period. Fixed horizon affects these labels.

## Fixed experiment

- Rules: never; first adjacent visible enemy; first enemy within two tiles;
  first adjacent visible enemy while HP <=70%.
- At most one berserk request per encounter, subject to the existing action mask.
  A failed request consumes this allowance; none were observed in training.
- Every non-berserk action is `fixed_action(..., 'pursue')`, not the learned
  directional scorer. No new items, stairs, retreat, movement or attack policy.
- Success requires full HP and 20 clean one-turn transitions on the same floor
  without observable threats/harm. Clean movement can count. Budget: 192 actions.
  Deaths and budgets both get recovery target zero, but are reported separately.
- Six simulator workers. 288 training episodes, then 32 validation episodes.
  No interim tuning. Harness errors stop fitting instead of becoming loss labels.

One initial feature vector per family: HP fraction, max HP, XL, AC, EV, visible
enemy count, maximum threat, adjacent count, nearest distance, ranged count,
unique count and berserk availability. No seed, name, turn, outcome or hidden
information. This deliberately small representation omits many existing rich
observation fields and is a limitation, not a replacement for the richer model.

Fit a depth-two multi-output regression tree, minimum three families per leaf,
to four empirical recovery probabilities averaged over six RNG offsets. Equal
family weighting. Choose the highest predicted rule only if its advantage over
never is at least 0.10; otherwise never. Ties favor never, then contact, then near.

Cross-fitting excludes all RNG siblings of the held-out seed before fitting.
Final fitting uses training families only; save the model before validation.
Evaluation selects a rule from initial observable features and looks up its
measured outcome in the complete paired matrix. It does not choose the winning
rule using that evaluated encounter's outcome. No separate chooser replay is
needed for this deterministic rule selection; executed rule traces are audited.

The final fitted tree chooses contact for >=2 initial visible enemies; otherwise
never for EV <=8 and near for EV >=9. These are correlations from 12 families,
not a justified general Crawl policy. Cross-fit performance warns against treating
this convenient split as robust knowledge.

## Evidence and reuse

Artifacts retain source snapshots, config/source hashes, raw states/actions,
death evidence, per-trial activation logs, paired outcome matrices, family
probabilities, cross-fit choices and final model. `audit_berserk_timing.py`
reconstructs every action, validates episodes and complete pair coverage, checks
seed separation, refits the model from training only, and recomputes both summaries.

All 320 episodes, 26,533 executed decisions and 201 berserk activations passed
the audit. No harness errors or no-turn stalls. 213 Python tests and 13 embedded
Lua checks passed. Source, report and progress log are version controlled; bulky
raw artifacts remain local in the ignored artifacts directory.

```sh
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/learn_berserk_timing.py --config .webtiles/bench/tactical/artifacts/action-direction-cycle-v1/config.json --output /absolute/new/berserk-run
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/audit_berserk_timing.py /absolute/new/berserk-run
.webtiles/bench/tactical/.rl-venv/bin/python -m unittest discover -s .webtiles/bench/tactical -p 'test_*.py'
```

Next: use early berserk as a strong comparison baseline, and improve learning of
when to withhold it. Preserve seed-level holdouts and include its regressions;
do not optimize against this ceiling-limited validation set. A future per-action
binary chooser needs outcome-labelled intermediate states, rather than pretending
this initial-context timing tree already supplies that capability.
