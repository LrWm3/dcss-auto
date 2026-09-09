# Augmented selector retraining v1

Completed a single fixed 1,500-epoch fit of the existing linear outcome selector
on the 180 verified rows from 31 mixed-outcome training variants. This learns
which goal/berserk permission to choose at encounter entry; it is not per-turn RL.
Older labels from before controller fixes were not mixed into this fit.

Candidate: `models/goal-selector-augmented-v1.json`. Baseline model and production
RC are unchanged. No deployment occurred.

| Recorded benchmark | Old model recovered | Candidate recovered |
| --- | ---: | ---: |
| All training-seed variants | 201/210 | 207/210 |
| Validation variants | 18/18 | 18/18 |
| Test variants | 18/18 | 18/18 |
| Separately reserved evaluation variants | 84/90 | 84/90 |

The candidate recovers on all 31 selected training variants. Across held-out
variants it ties the baseline at 120/126: two baseline deaths improve, but two
baseline recoveries regress. Always pursuing without berserk reaches 121/126
on this benchmark. There is no demonstrated held-out improvement.

Evaluation uses the already audited exhaustive strategy-outcome matrix, including
all-win, all-loss and incomplete variants, not just selected training scenarios.
The candidate was frozen before evaluating these rows; no hyperparameter tuning
or refitting followed the results. Six lexicographically first changed held-out
choices were additionally replayed from fresh resets, selected without consulting
their outcomes: all six match and pass endpoint audits. This is not a fresh replay
of every selector choice and not a full-game benchmark. Variants share parent
seeds; these are correlated synthetic cases, and held-out scenarios have already
been inspected during earlier work.

164 Python tests and 13 Lua checks pass. The next useful investigation is the two
held-out regressions, rather than deploying on the strength of training accuracy.

## Reproduce

Use a new output directory, Python with `pexpect`, and the same sources/engines:

```sh
export DCSS_TACTICAL_ENGINE="$PWD/crawl-0.35/crawl-ref/source/crawl-tactical-augment"
export DCSS_TACTICAL_AUGMENT=1
python .webtiles/bench/tactical/retrain_augmented_goals.py \
  .webtiles/bench/tactical/artifacts/augmentation-all-v4 \
  .webtiles/bench/tactical/artifacts/goals-augmented-trained-NEW
```

Results: `artifacts/goals-augmented-trained-v1`.
Checksums: [evidence/goals-augmented-trained-v1.json](evidence/goals-augmented-trained-v1.json).

