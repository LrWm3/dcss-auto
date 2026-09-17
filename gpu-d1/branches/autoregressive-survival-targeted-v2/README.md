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
