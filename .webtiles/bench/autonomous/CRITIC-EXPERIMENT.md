# Frozen-policy critic experiment

`critic_experiment.py` collects complete sampled-policy games from the competent
PPO initial actor. The actor and its spatial encoder remain frozen. There is no
PPO update, actor optimizer, or promotion. An actor tensor digest audits this.

Compare two newly trained value heads on identical data:

- `state_only`: frozen spatial/inventory/global context (544 floats).
- `navigation`: same context plus mean/max pooled legal-action descriptors,
  including route distances and visit memory. Pooling is order invariant.

This deliberately inexpensive ablation tests whether missing inputs help. It
does not test end-to-end critic representation learning; pooled descriptors can
lose arrangements. Existing zero-action PPO critic weights are not reused.

Uniformly sample one pre-action state per 16 decisions (random phase per game).
Store compact float32 contexts, descriptors, and scalar action/score traces,
not duplicated full 100k-float observations. Inputs are reproducible using the
recorded engine seed, policy sampling seed, actor hash and environment hashes.
This is a specialized calibration dataset, not a replacement snapshot archive.

Target = (true terminal training score - current training score) / 1000.
Native and exploration scores remain separately reported. No reward changes.
Games can run for 12,000 total decisions, retaining the 2,000-per-floor safety
limit. Cutoffs and simulator errors are reported, never used as terminal labels.
Consequently calibration is conditional on completed games: inspect censoring
rates and floor coverage before generalizing to long surviving games.

Default split: 32 training seeds, 8 fresh validation seeds in namespace C,
8 fresh test seeds in namespace D. Namespace E remains untouched. No old
evaluation trajectories enter training. Train-only feature normalization and
equal-per-game weighting prevent long games dominating. Validation selects the
epoch; test is evaluated only afterward. Report MSE, MAE, explained variance,
and a train-mean constant baseline. Lower test MSE is evidence for prediction,
not evidence of better gameplay. This small experiment does not establish
statistical significance or justify actor-policy promotion.

Run with the RL venv:

```sh
python .webtiles/bench/autonomous/critic_experiment.py \
  --initial .webtiles/bench/autonomous/artifacts/ppo-pilot-01/initial.pt \
  --output .webtiles/bench/autonomous/artifacts/critic-mc-01
```

`latest_status.json`, `collection.json`, `comparison.json`, and independent
critic checkpoints persist results. Identical-config restart reuses completed
games; an interrupted fit restarts deterministically from its compact dataset.
An interrupted individual game restarts from its seed. Engine failures are
isolated and recorded; too few completed games produces an explicit invalid
experiment instead of invented labels. Low-space guard pauses below 20 GiB.

## Initial correctness checks (2026-09-14)

- Six critic tests and eight existing PPO tests passed.
- `artifacts/critic-mc-smoke-01`: six 64-decision games, all censored and correctly
  excluded; no simulator errors or actor changes. Insufficient labels was
  correctly reported as an invalid calibration experiment.
- `artifacts/critic-mc-smoke-02`: six complete games, zero errors/cutoffs,
  real Monte Carlo labels, both fits and validation/test reports completed;
  actor digest unchanged. Two training games/two epochs is only a plumbing
  test: both critics were worse than the constant baseline on its two test games.
- The main `artifacts/critic-mc-01` run uses different seeds and the default
  32/8/8 split. No actor-policy improvement is claimed.

## Main experiment completed (2026-09-14)

All 48 game attempts finished without simulator errors. The actor remained
unchanged. One test game hit its administrative cutoff and was excluded from
eventual-terminal-return labels, leaving 32 training, eight validation and
seven usable test games. This exclusion is specific to Monte Carlo terminal
targets; it does not reinstate the old rule disqualifying bounded-score games.

Validation selected state-only epoch 2 and navigation epoch 1. Test results:

| Predictor | Seed-balanced MSE | Explained variance |
| --- | ---: | ---: |
| State only | 2.426218 | -0.0114 |
| Navigation descriptors | 2.338205 | 0.0301 |
| Train-mean constant | 2.383386 | 0 |

The navigation head's MSE is about 3.6% lower than state-only and 1.9% lower
than constant. Further epochs worsened validation. See the saved
[comparison](artifacts/critic-mc-01/comparison.json) and
[status](artifacts/critic-mc-01/latest_status.json).

The subsequent session review found that one high-return game accounted for
about 94% of test squared error and all net navigation advantage. The other
six games' mean MSE change was +0.00458 (worse). The seven-game paired change
was -0.0880 with a descriptive bootstrap interval of -0.2788 to +0.02134.
This small, correlated-snapshot dataset does not establish reliable prediction
improvement, much less better gameplay. The actor encoder was frozen and
legal-action descriptors pooled: this was not end-to-end representation
learning. See session S287 in the [source index](../history/SESSIONS.md) and
the [experiment ledger](../EXPERIMENT-LEDGER.md).
