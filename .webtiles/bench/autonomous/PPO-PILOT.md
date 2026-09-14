# General policy PPO pilot

This replaces action-preference refitting **for this experiment**, not the
historical autonomous learner or its saved runs. No champions are overwritten.

## Input audit

The conservative retry's second evaluation game performed 1,565 MELEE actions:
1,477 against bushes and 39 against plants. These were real time-consuming
attacks (zero had a zero-turn delta), not a transport stall. Enemy scanning
excluded firewood but legal melee actions still targeted it. The action encoder
therefore received no target monster features for those attacks.

With `DCSS_TARGET_DETAILS=1`, the bridge exports player-visible `action.target`
details and the encoder uses them when the threat list has no corresponding
entity. The observation declares `visible-melee-target-v1`. No action is banned,
no tactical reward is added, and the feature tensor dimensions do not change.
Historical mode remains opt-out. Both baseline and candidate evaluation use the
corrected interface, so old evaluation scores cannot serve as this baseline.

The same 2,000-transition trace passed the score-difference telescoping check:
sum of score changes = final minus initial training score, 521.9619883769965.
This includes the existing x10-native plus capped exploration objective.

## Algorithm

- Existing V6 spatial/entity/action-conditioned policy, variable legal actions.
- Softmax-sampled on-policy actors, no teacher, uniform-epsilon substitute, or
  greedy collection. Full behavior log probabilities are retained.
- Reward `(training_score_after - training_score_before) / 1000`, gamma 1.
  At gamma 1 these sum to the score difference, including negative changes.
- Independent state-value critic uses the existing separate encoder, with zero
  action features. It starts from the policy representation and a zero output
  head, not an old log-score/Q critic. No new shared actor/critic parameters.
- GAE lambda .95. Actual terminal states have no bootstrap. Chunk boundaries
  and administrative cutoffs use V(next_state), without leaking GAE into the
  next episode. A chunk cutoff normally saves and continues the same game.
- PPO clipping .1, entropy coefficient .001, actor Adam LR 1e-5, critic Adam
  LR 3e-4, four epochs, batch size 32, gradient norm cap .5. Ragged batching
  encodes each observation once rather than once per legal action.
- Each epoch checks exact KL against all collected action distributions.
  Mean >.01 or any state >.15 rolls back both networks and both optimizers and
  stops the update. Nonfinite parameters also reject the epoch. The batch must
  match the collecting policy before training starts.

These controls do not promise monotonic improvement or solve long-horizon
credit assignment. In particular, initially the critic is weak. This is a
bounded test of a standard collection/update loop, not a strong Crawl player.

## Pilot layout

Default: two independent training sampling runs, each four cycles, eight actor
lanes, 256 decisions per lane per cycle (up to 16,384 training decisions total).
Both start from the same competent policy. Training randomness/data differs;
these are not independently bootstrapped network initializations.

One quarter of the lanes rotates to fresh training seeds each cycle, while the
rest keep their exact saved games and action-sampler state. Deaths and
administrative budgets also start new games. The per-floor limit remains 2,000;
the training total-game safety cap is 100,000. Individual failed actor chunks
are recorded and excluded, never labeled as deaths or used as partial replay.

Eight fresh quarantined **development** seeds are fixed for paired evaluation
at baseline, cycles two/four, and final greedy-policy diagnostics. The primary
pilot evaluation samples softmax actions, matching the policy PPO optimizes;
greedy deployment is evaluated separately. Evaluation sampling seeds are paired
across models. Each evaluation has a 2,000-decision total pilot budget as well
as the 2,000-per-floor cap. Scores at cutoffs are actual current scores.

Native and exploration-inclusive scores are both reported. The latter is the
training objective; native score remains independently visible. The final-test
0xE namespace is untouched. No automated promotion, confidence claim, or
learning guarantee is made from these small development evaluations.

## Run and resume

From the repository root:

```
.webtiles/bench/tactical/.rl-venv/bin/python \
  .webtiles/bench/autonomous/train_ppo_pilot.py \
  --initial .webtiles/bench/autonomous/artifacts/v6-visits-01/candidate.pt \
  --output .webtiles/bench/autonomous/artifacts/ppo-pilot-01
```

The entry point sets all required representation/objective/interface modes.
Repeat the exact command to resume. Configuration and relevant source/binary
hashes must match. Completed actor chunks and evaluations are reused. Each
cycle atomically saves the model, both optimizers, actor snapshots, budgets,
and sampling RNG states. The candidate carries forward even without promotion.
Incomplete artifacts are preserved; retry snapshots use new names.

Artifacts include `config.json`, `initial.pt`, `latest_status.json`,
`evaluation-seeds.json`, `comparisons.json`, per-cycle compressed on-policy
trajectories, `collection.json`, `training.json`, `training-state.pt`,
`candidate.pt`, and paired evaluation results. Failed actors write
`failure.json`. No old experiment data is deleted. Existing 20 GiB pause and
22 GiB resume disk protection remains active. The pilot is finite (eight total
training cycles); it does not introduce an unbounded replay archive.

Smoke: add `--smoke` and use a new output directory. This runs two actual
collection/update/evaluation cycles with tiny budgets. Unit tests:

```
cd .webtiles/bench/autonomous
../tactical/.rl-venv/bin/python -m unittest test_ppo_pilot
```

Legacy nonspatial model tests must run in a separate process from this test
module, because representation selection is intentionally import-time.

Validation artifacts:

- `artifacts/ppo-smoke-03`: two completed real collect/update/evaluate cycles,
  64 transitions, no actor errors. All 16 actor parameter tensors changed
  (combined L2 change .01657469); tiny smoke evaluations tied, not an improvement
  claim. `resume-audit.json` confirms eight completed artifacts were reused
  without recollection or retraining.
- `artifacts/ppo-interface-smoke-02/visible-target-audit.json`: live bush target
  details passed. `determinism/result.json`: full observations matched for eight
  steps on each of two exact restored continuations.
- 57 unit tests passed across separate PPO and legacy-model processes.

Background pilot: `codex-ppo-pilot-01.service`, results/status under
`artifacts/ppo-pilot-01`. Use the exact command above to resume after interruption.

## Fresh frozen-checkpoint suite

`evaluate_ppo_suite.py` compares the baseline plus both runs' cycle-two and
cycle-four checkpoints, without training or promotion. Default: 40 fresh 0xD
confirmation seeds, five policies, 200 games, four workers, sampled-softmax
actions, the pilot's same 2,000-decision budgets. Engine/interface hashes must
match the pilot. Checkpoint hashes, seeds, and paired policy-sampling seeds
are fixed before evaluation. New seeds are checked against existing artifact
JSON manifests/results before the suite is published; 0xE remains unused.

```
.webtiles/bench/tactical/.rl-venv/bin/python \
  .webtiles/bench/autonomous/evaluate_ppo_suite.py \
  --source .webtiles/bench/autonomous/artifacts/ppo-pilot-01 \
  --output .webtiles/bench/autonomous/artifacts/ppo-fresh-suite-01
```

Repeat the exact command to resume. Individual errors are reported, not turned
into zero scores or silently removed from paired comparisons. Results include
paired native/training-score changes, medians, 95% and 98.75% approximate paired
bootstrap intervals, and sensitivity to removing the largest positive paired
gain. The wider interval accounts for four candidate comparisons via Bonferroni;
finite-sample bootstrap coverage is still approximate, not a promotion guarantee.

`ppo-fresh-suite-smoke-01` completed ten short games without errors. Constant-
delta, tie, pairing, and outlier-sensitivity assertions passed before launch.
Background unit: `codex-ppo-fresh-suite-01.service`. The status file is
`artifacts/ppo-fresh-suite-01/latest_status.json`; disk backpressure remains active.

## Completed results (history audit, 2026-09-14)

Both four-cycle training replicates completed, totaling 16,384 training
decisions without actor errors. Small development evaluations improved at some
checkpoints, but that did not replicate in the fresh suite: all 200 games
completed without evaluation errors. Mean native scores:

| Policy | Fresh 40-seed mean |
| --- | ---: |
| Initial baseline | 94.15 |
| Run 1, cycle 2 | 65.85 |
| Run 1, cycle 4 | 58.875 |
| Run 2, cycle 2 | 48.20 |
| Run 2, cycle 4 | 62.95 |

All candidate means were lower; uncertainty intervals included zero. No
promotion or reliable improvement is established. Preserve the original
[fresh-suite artifacts](artifacts/ppo-fresh-suite-01), and see
[signal diagnosis](PPO-SIGNAL-DIAGNOSIS.md) and the
[full ledger](../EXPERIMENT-LEDGER.md) for subsequent diagnostic work.
