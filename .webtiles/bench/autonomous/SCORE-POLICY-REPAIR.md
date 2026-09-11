# Score-policy repair — September 11, 2026

Ready for another training launch; no long-running job has been started.
General held-out improvement remains unproven.

## Repairs

- Faith removal: explicitly selected REMOVE actions accept the matching item
  confirmation. Other unimplemented confirmations cancel instead of blocking.
- Evoked invisibility: disable Crawl's informational invisibility targeter;
  activation still applies the real game's costs and effects.
- Failed actions now retain `failed_action.json`, including the attempted
  semantic action and its pre-action observation, not just the previous move.
- Ordinary scored gameplay now changes the policy, not just its separate
  critic. Log exact epsilon-greedy behavior probabilities; use actual log-score
  returns, a critic baseline, clipped importance weights, and reference KL.
  A proposed ordinary-play update exceeding mean KL .01 is rolled back along
  with its optimizer state. The limit is per cycle on sampled training states,
  not a global guarantee of unchanged behavior.
- Remove repeated teacher cloning from each update. Behavioral cloning still
  initializes a brand-new run; persistent learner weights survive rejection.
- Counterfactual continuations that reach their fixed decision horizon now use
  official live scores. Errors/missing scores remain unlabelled. Comparison IDs
  include the continuation policy, checkpoint, score protocol, and horizon;
  old terminal-only preference labels do not enter the new policy update.
- Archive sampling covers encounter starts, healthy states, danger states, and
  general coverage rather than preferring the most recent death snapshots.
  Reserve the fourth snapshot slot on each floor for another encounter start.
- Feature v5 includes numeric resistances, willpower, poison/fire, equipment
  properties, eight position-sorted monsters' wounds/defences/status, candidate
  item/target properties, and destination cloud type. This is still a compact
  feature model, not an exhaustive observation encoder.
- Migrate v4 network weights into expanded input layers with zero-initialized
  new-property weights. Preserve learned logits/values within floating-point
  tolerance; reset incompatible optimizer tensors explicitly.

## Validation

`CRAWL_STORAGE_LIVE_TEST=1 .../python -m unittest discover -s
.webtiles/bench/autonomous -p 'test_*.py'`: **65 tests passed**, including live
in-place snapshot, RNG restoration, and identical future observation tests.
New tests check numeric feature sensitivity, both-head migration, score-driven
policy changes despite contradictory teacher labels, behavior probabilities,
KL bounds, cutoff labels, and stratified sampling.

Historical prompt fixtures were copied, retaining original saves, then given
the current bridge. `smoke_prompt_repairs.py` verified:

- Evoke Invisibility: turn 678 → 679; invisible status present.
- Remove faith amulet: turn 945 → 951; item no longer equipped.
- Both returned the next structured observation in approximately 4 ms.

Artifacts: `artifacts/score-policy-v2-prompt-smoke/results.json`.

Two complete, isolated orchestration cycles used the migrated real champion
and cycle-0033 learner, two actors/cycle, 180 decisions/floor, 360 overall, two
screen seeds, and 24-decision counterfactual continuations:

- Four actor episodes, 720 decisions, zero recorded failures.
- 24/24 counterfactual action estimates scored; all 48 continuations reached
  their horizon alive and now contribute labels instead of being discarded.
- Three ordinary score-policy optimizer steps per cycle on 256 sampled rows.
- Counterfactual training found three then six unequal-return comparison
  groups; all reported better-minus-worse logit margins increased.
- Cycle two used cycle one's committed learner, not V0.
- Both automatic evaluations completed. Screen scores were champion [4, 8],
  first candidate [164, 8], second candidate [4, 8]. Neither was promoted.
  These tiny, short smoke evaluations are not evidence of general improvement.

Artifacts: `artifacts/score-policy-v2-loop-smoke/latest_status.json`,
`learner/*.ready.json`, `evaluations/paired_seeds.jsonl`, and
`rollouts/counterfactual_results.jsonl` beneath that run.

## Next launch

`artifacts/foundation-general-training-v5` is prepared, not running. Its
`lineage.json` records source/destination checkpoint hashes. Champion remains
the original V0; initial learner is the latest completed cycle-0033 candidate.
The old partial cycle 0034, old replay and historical evaluations remain in v4.
Previous completed-cycle result summaries carry the weakest-seed curriculum
forward; no old transition labels were copied. Existing 20 GiB disk pause,
eight-cycle heavy retention and independent promotion checks remain enabled.

```bash
./train_crawl_agent \
  --run-dir .webtiles/bench/autonomous/artifacts/foundation-general-training-v5 \
  --cycles 2
```

This command is documented for the next authorized launch, not executed by
the repair task. Watch score distributions and paired held-out results: a
functioning return-driven update is necessary but does not guarantee progress.
