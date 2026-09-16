# Tactical learning follow-up

Question: do inconsistent retreat and pocket-defense decisions improve with more
ordinary training, targeted experience, or a different representation?

Queue: `branches/vision15-tactical-next-v1/scripts/run_experiment.py`, using
`.venv/bin/python`. Outputs live in ignored `learning-runs/vision15-tactical-next`;
compact diagnostic reports go in `results/tactical-next-*`.

## Training comparisons

Each row has seeds 0, 1, 2 for both ordinary placement and one-third clumped
placement: six jobs per row, 24 jobs total. Jobs run sequentially on the GPU.

| Experiment | Start | End | Change |
|---|---|---|---|
| continue | Existing 30M checkpoint | 100M | None |
| targeted | Same 30M checkpoint | 100M | 10% of newly selected episodes are tactical scenarios |
| enemy_set | Fresh | 30M | Shared enemy encoder and masked sum pooling replace ordered enemy records |
| d4_exact | Fresh | 30M | Average policy logits and critic values over all eight orientations |

Continuation checkpoints preserve model, optimizer, RNG, live worlds, and counters.
Seed 0 ordinary uses its original simulator library because its serialized state
layout differs from the later clumped implementation. The original libraries are
also retained for the other ordinary-floor training jobs. Parameters, rewards,
observations, and PPO settings otherwise remain unchanged: 24 enemies, 2048 turns,
15x15 wall-blocked vision, LOS wake, seen-floor scalar, +1 kill, +3 clear,
-4 death, +0.002 newly seen floor, -0.001 turn. Batch 512, rollout 64,
four PPO epochs, minibatch 4096, learning rate 0.0003.

The targeted comparison branches at exactly the same checkpoint as its unchanged
control. Current episodes finish normally. Thereafter 10% of episode selections
use tactical worlds. This is **10% of episodes, not decisions**; short tactical
battles can contribute a much smaller fraction of training decisions. Both
fractions and outcomes are recorded. Ordinary worlds are paused during tactical
episodes; model observations do not contain a curriculum indicator.

The enemy-set model retains enemy spatial coordinates and visible grid information.
It changes parameter count as well as structure, so this is a representation screen,
not a capacity-matched causal test. D4 averaging uses eight views for every policy
call, including evaluation. It enforces policy consistency but adds compute; it is
distinct from the earlier random per-episode augmentation. Simulator tie-breaking
is not guaranteed rotation-invariant, so enforced policy symmetry is a hypothesis,
not proof that the resulting action is optimal. Report training time,
parameter counts, and decisions alongside performance. These two changes are tested
separately, not combined.

## Targeted experience and held-out layouts

64 training layouts: hallway or diagonal pocket, room-depth parameters 3 or 5,
room half-widths 2 or 3, and all eight orientations. Enemy starts are two rows
of three. Initial health is 6–18, elapsed time is 0/256/512, and battles contain
three or six awake enemies with either weak or tough rosters. Enemy energy varies.

These are combat subepisodes with only three or six required enemies remaining.
Clearing them earns the usual +3; this changes the frequency/ease of reaching the
clear reward as part of the curriculum. No optimal actions, forced retreats,
extra tactical rewards, or goal labels are supplied to the learner.

32 held-out layouts use room-depth parameters 4 or 6 and half-width 4.
Hallway goals lie two tiles beyond that depth; diagonal pockets use a two-cell
diagonal tail. The stored distance parameter is not the complete retreat length. Exact floor geometries
are checked disjoint from training. They also differ from the established retreat
suite. This tests related geometry generalization, not wholly novel tactical rules.
Native movement, regeneration, energy, combat, observations, and reward code are
unchanged. The custom kernel only initializes scenario states.

## Evaluation

- Ordinary held-out validation at training checkpoints; test maps remain unused.
- At 50M, 75M, and 100M for continuation pairs, and 30M for architecture pairs:
  rerun one-step hallway, three-step hallway, diagonal pocket, and distant pocket
  at distances 4 and 6. Include natural behavior, forced-retreat controls, and
  scripted controls. Scripted results must exactly match the existing reference.
- Every evaluated model also sees the same frozen bank of 3,072 observations from
  all six existing models: retreat-route steps and first pocket contact. Compare
  wait probabilities, orientation sensitivity, and sensitivity to reversing enemy
  record order. Frozen observations are never used for training. These are
  policy-output comparisons, not counterfactual survival estimates.
- Run 512 sampled episodes on the separate held-out tactical layouts. Report
  clears, deaths, unresolved at a 512-action diagnostic cap, and actions consumed.
  The diagnostic cap is separate from the native 2048-turn timeout.

Training continuations are assessed at equal additional decisions; representation
models are compared with existing 30M baselines at equal decisions. Training time
is reported separately. Three seeds help reveal consistency, but do not support
precise significance claims for small differences. Repeated episodes and rotations
are not independent training seeds. A negative curriculum result needs to be read
alongside its actual decision exposure.

## Preparation and checks

Run `scenario_maps.py`, `assets.py`, `preflight.py`, and `capture_frozen.py` before
launching the queue. Preflight checks geometry, original initialization parity,
enemy permutation invariance, D4 actor equivariance / critic invariance, finite
gradients, episode switching, and exact environment resume. Smoke tests exercise
PPO updates and checkpoint resume for all four experiment types. The shared
diagnostic loader supports the new model architectures without changing existing
models' evaluation behavior.

The queue checkpoints to disk, is resumable, and stops on failed validation.
Full latest state plus compact milestone weights are retained under a 4 GiB suite
budget and 10 GiB free-space reserve. Generated maps, native binaries, and frozen
tensors live in ignored asset directories; source, metadata, and reports are tracked.
