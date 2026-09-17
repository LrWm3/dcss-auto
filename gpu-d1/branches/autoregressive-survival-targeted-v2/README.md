# Targeted survival practice

Follow-up to `autoregressive-survival-v1`, starting from its exploration arm at
35,000,320 cumulative decisions. The hypothesis is that varied longer approaches
to shelter will fix retreat reversals and exposed fighting seen in remaining losses.

## Failure diagnosis

`results/autoregressive-survival-failures.json` contains paired greedy-policy and
cover-controller rollouts from identical initial states and RNG. In the existing
512-episode tactical panel the policy lost 98 episodes; the cover controller won
62 of those. This establishes alternative successful trajectories, not that every
such death is reliably preventable: different actions consume RNG differently,
and the controller also loses episodes that the model wins.

Diagonal pockets account for 44 policy deaths, 29 of which the controller clears.
26 of the 44 deaths occur without reaching the designated pocket. Example episode
24 starts at full HP, retreats southeast one square, then returns northwest into
the approaching group. It dies surrounded. The cover controller keeps retreating
five squares and wins. Episode 29 similarly reverses, circles the room, and fights
exposed. Other deaths happen after reaching cover, or from low initial HP; these
are not all errors of navigation.

## Controlled experiment

Both arms continue the same policy **and optimizer** for 5,000,192 additional
model decisions, evaluating after 1,000,448 and 5,000,192. Both reset practice
worlds and counters, while preserving ordinary-floor simulator state and the
training RNG. This avoids restoring old practice states onto a changed map table.

- Control: continue the existing 64-map tactical training distribution.
- Targeted: 128 training maps, consisting of all 64 original maps plus 64 new
  approach layouts (eight base geometries in all eight D4 orientations).

Each allocates 51 of 512 worlds to practice, at sampling temperature 5; all other
worlds use ordinary floors at temperature 1. Evaluation always uses temperature 1,
with sampled and type-first greedy actions. Added layouts vary pocket distance,
room aspect ratio, and an asymmetric clipped corner. No demonstrations, scripted
actions, goal observations, or auxiliary rewards are added.

All other training settings remain fixed: low-level MOVE/ATTACK directions,
WAIT/REST, wall LOS, +1 clear and -0.00001 per physical turn, navigation-only
imitation anchor, 24 enemies and 2048 turns on ordinary floors. Tactical episodes
retain the original randomized 1/6-enemy, HP 6/12/18 reset distribution. The native
simulator and tactical reset library are reused unchanged.

Evaluation includes the original 64-layout development panel, 64 **new** approach
layouts (eight base geometries, disjoint from both training sets even after D4
transforms), and the existing ordinary-floor validation panel of 1,024 episodes.
The original tactical panel was used to diagnose failure and is now a development
benchmark. The new panel is fixed before training; its initial greedy clear rate
is 56.84%. Eight rotations/reflections of a geometry are not independent layouts.
This is a one-training-seed screen, not an estimate of PPO seed variability.

## Reproduction

Use `gpu-d1/.venv/bin/python` with these scripts:

1. `scripts/diagnose.py` records old-panel failures and example trajectories.
2. `scripts/target_scenarios.py` checks split separation and prepares map assets.
3. `scripts/run_targeted.py` launches the two continuations sequentially and resumes
   interrupted work. Its manifest records source/asset/checkpoint hashes.

Checkpoints stay under ignored `learning-runs/autoregressive-survival-targeted`,
with a 4 GiB suite limit and a 10 GiB free-space minimum. Raw comparison results
are `results/autoregressive-survival-targeted.json`; the before-training baseline
and diagnostic controllers are `results/autoregressive-survival-targeted-initial.json`.
The branch copies v1's implementation for isolation; the runner adds configurable
practice map count and a second tactical evaluation panel.

## First comparison completed

Each continuation finished at 40,000,512 cumulative decisions. Greedy clear rates:

| Evaluation | Source 35M | Control +5M | Targeted +5M |
|---|---:|---:|---:|
| New approach panel, 512 episodes | 56.84% | 50.78% | **83.20%** |
| Original tactical panel, 512 episodes | 80.86% | 74.41% | 77.73% |
| Ordinary floors, 1,024 episodes | 94.34% | 94.43% | 94.24% |

Ordinary sampled clears were 96.09%, 96.68%, and 96.48%, respectively.
On the new panel sampled clears improved from 50.39% to 83.01% (control 46.48%).
The targeted arm already reached 82.62% greedy at +1M; most of its greedy gain
arrived early, although sampled behavior continued improving afterward.

Four fresh encounter seeds, totaling 2,048 new episodes on the fixed new panel:

| Policy | Greedy clear |
|---|---:|
| Source | 54.54% |
| Matched control | 47.95% |
| Targeted | **84.13%** |
| Privileged cover controller | 85.11% |

Targeted-minus-control is +36.18 percentage points, with a paired bootstrap
interval of [31.49, 40.33] points, resampling eight base geometries and keeping all
orientations and encounter seeds together. All eight base geometries improved.
This interval describes this geometry distribution, not independent training seeds.
The difference from the cover controller was -0.98 points, interval [-2.20, 0.15];
there is no evidence the learned policy beats that diagnostic controller.

Fresh-seed shelter arrival rose from 41.55% to 78.66%; mean turns with multiple
adjacent enemies fell from 12.21 to 2.28. The controller was at 2.32 such turns.
These results support learning useful retreat behavior on the new family.

However, the original square-pocket examples 24 and 29 still die. Original-panel
pocket clears are unchanged at 65.63%, and separated-group clears regress from
89.84% to 74.22%. The model can choose a nearby exposed corner instead of the
farther one-neighbor pocket. Consequently this is a targeted improvement, not a
uniformly stronger replacement. `results/autoregressive-survival-targeted-remaining.json`
records this remaining failure and its example trajectories.

Control and targeted training took 163.97 and 166.82 seconds, respectively
(5.51 minutes total, excluding evaluation and preparation). A report-only error
at control +1M produced NaNs for absent scenario families; those summaries now
return null. The intact policy/optimizer/simulator checkpoint was resumed after
sanitizing only its report history. The interrupted +1M compact snapshot was not
written; its evaluation numbers remain in the curve. The suite manifest records
the reporting source change in `evaluation-recovery.json`. Reported pipeline wall
time after recovery excludes the initial pre-recovery segment; training time is
cumulative and includes it.

## Adaptive retention follow-up

`diagnostics/survival-targeted/balanced.py` adds a third arm, from the **same 35M
source**, with the same +5M budget, 51 practice worlds, temperature, rewards,
optimizer state and ordinary-world continuation. The completed control is reused.
The only intervention is again the training scenario distribution:

- 64 original scenario entries;
- 64 prior new approach entries;
- 64 untrimmed rooms where genuine shelter is farther than an exposed corner;
- 64 additional two-sided enemy-group scenarios.

Map entries are sampled at episode reset. Equal entry counts do not imply equal
numbers of decisions, because scenario durations differ. The 51/512 allocation
fixes the total practice decision count. A further 64-map test panel is generated
before training and checked disjoint from training and the previous held-out maps.
The first new panel is now a development benchmark for this adaptive follow-up.

Run `diagnostics/survival-targeted/confirm.py --balanced --panel far` for evaluation
on the additional geometry panel and four fresh encounter seeds. `--panel novel`
and `--panel original` check the earlier panels. All use greedy model actions at
normal temperature and the same initial state distribution for every checkpoint.
