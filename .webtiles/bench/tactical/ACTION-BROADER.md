# Broader training-only corrections — 2026-09-10

Run: `artifacts/action-broader-v1`. Parent: `action-dagger-v1/round-3.zip`.
No PPO, production deployment, or test-set access. No failed validation trajectory
was added to training.

## Results: less waiting, no overall policy gain

| Frozen policy | Expanded training recovered / died / timed out | Validation recovered / died / timed out |
| --- | --- | --- |
| Starting correction model | 22 / 13 / 1 | 6 / 2 / 0 (previous run) |
| Broader correction model | 19 / 12 / 5 | 6 / 2 / 0 |
| Pursuit teacher | 23 / 8 / 5 | 8 / 0 / 0 (previous run) |

The final model regressed on fixed training replays and did not improve validation
recovery count. Keep the previous checkpoint as the reference; do not deploy this
one. The original 18 training variants fell from 15 to 14 recoveries, while the
18 added variants fell from seven to five (teacher: eight on the added variants).

Three previously recovered training variants stopped recovering: Eustachio seed
83019003/RNG-2 became a death; Blorkula/hound seed 83017005/RNG-0 and RNG-2 exhausted
the budget. Two previous deaths became budget truncations, not recoveries: Edmund
83018003/RNG-1 and Maggie 83018004/RNG-2. Outcomes are not interchangeable.

Validation changed which cases failed: water-moccasin RNG-0 now recovers, but
ribbon-worm RNG-1 now dies; water-moccasin RNG-1 still dies. Equal aggregate
recovery counts conceal that trade-off. No extra fit was made after these results.

| Training rollout | Adjacent-enemy decisions | Waits among those decisions | Waits when teacher would act |
| --- | ---: | ---: | ---: |
| Starting model | 455 | 133 (29.2%) | 180 |
| After first fit | 459 | 11 (2.4%) | 18 |
| Final model | 520 | 3 (0.6%) | 3 |
| Teacher | 352 | 0 | 0 |

These are matched initial cases but different trajectories and lengths, not
matched decision states. The unwanted waiting nearly disappeared **in training**
without improving the success criterion. Directional disagreements remained;
after the first fit, common errors included north instead of east/northeast and
northwest instead of north. This does not establish that direction errors alone
caused every failed recovery. On validation the final model still waited at
38/144 adjacent-enemy decisions and waited 39 times when the teacher would act.

Two rounds added **4,308 labels and 567 disagreements** (2,074/342 then 2,234/225).
Final aggregate data: 8,608 examples. Training-label accuracy was 1,939/1,960
directions, 8/8 threatened waits and 6,639/6,640 other waits. Once threatened waits
appeared, the fixed sampler allocated that group 20% mass despite only eight
examples; this is a potential overfitting concern, not a cause isolated by this run.

The next experiment should test a clearer spatial/directional representation and
guard against over-weighting tiny strata, using training-only diagnostics and a
fixed comparison budget. Simply repeating this same data/fit loop is not supported
by the current result. Teacher performance also limits what pure pursuit imitation
can achieve on the harder added encounters.

All 4,308 new labels passed the independent teacher/action/mask/observation-history
audit. All 188 episode records passed transition/outcome auditing: 90 recoveries,
48 deaths, 14 budget truncations and 36 administrative preflight closes. These
pooled counts span different policies and are not a win rate. No harness errors
or no-turn stalls occurred. 203 Python tests plus 13 embedded Lua checks passed.

## Fixed experiment

Use all 12 control encounters in the existing audited `character-training-v1`
training archive, rather than only the six used in the pilot. Each has three
gameplay-RNG offsets (0/1/2), giving **36 training variants from 12 seeds**.
This reuses archived encounters, not a new mining campaign.

The six added seeds are 83018002, 83018003, 83017005, 83019004, 83019002 and 83018004:
another Eustachio, Edmund, Blorkula with a hound, a water moccasin, another hound,
and Maggie with a bombardier beetle. Selection includes **all remaining training
control rows**, not hand-picked failures from validation. All are checked against
the existing seed split. The original 18 action cases and eight validation cases
remain unchanged; only newly derived training RCs are created.

All 18 new variants passed two deterministic 16-action preflight replays each:
**36 replays, 576 actions, no zero-turn requests**, matching parent initial states
and repeat trajectories. Existing cases retain their earlier preflight.

Starting from the previous final correction model, perform **two fixed rounds**:
the learner controls every action in all 36 training variants, the pursuit teacher
labels those learner states, and 10 epochs fit all accumulated labels. Retain the
previous 4,300 examples. Same stratified sampling, disagreement weighting, actor,
features, masks, teacher and action budget as `ACTION-DAGGER.md`. Sampling seeds
51/52, Adam .0003, batch 128. No adaptive stopping or intermediate validation.

After fitting, replay the final model and the pursuit teacher on all 36 training
variants. Evaluate only the predetermined final model on the eight unchanged
validation variants. The first collection round provides a matched starting-model
training baseline. Validation is still four encounter families from one previously
studied seed, not a pristine or statistically broad final test.

## Combat metrics

In addition to recovery/death/budget outcomes, `combat_metrics` reads raw states
and action audits to count:

- Decisions with a visible adjacent enemy.
- Waits at those adjacent-enemy decisions.
- Waits when the masked pursuit teacher would instead move or attack.

The second metric does not assume every adjacent enemy is safely attackable;
the third measures disagreement with the teacher and also includes approaching
distant enemies. These are diagnostics, not rewards or runtime action overrides.
A regression test separates adjacency from distant-enemy teacher disagreement.

## Reproduce

Use the environment and prerequisites from `ACTION-IMITATION.md`, plus the saved
parent correction run. Outputs must be new directories.

```sh
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/broaden_action_training.py --parent .webtiles/bench/tactical/artifacts/action-dagger-v1 --output /absolute/new/broader-run
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/audit_dagger_labels.py /absolute/new/broader-run
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/audit_action_episodes.py /absolute/new/broader-run
.webtiles/bench/tactical/.rl-venv/bin/python -m unittest discover -s .webtiles/bench/tactical -p 'test_*.py'
```

Source snapshots, split/config/engine/checkpoint provenance, per-case arrays,
teacher/executed actions and game evidence are retained in the artifact directory.
