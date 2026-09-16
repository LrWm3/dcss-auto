# One-third clumped placement, seed 0 to 30M

2026-09-16. Test whether more concentrated encounters improve ordinary-layout
survival. Train a fresh seed-0 policy to 30M decisions, using the same initial
weights, PPO settings, 256 training layouts and 959 observations as the
seen-floor / +1 kill / +3 clear / -4 death experiment. Keep 24 normal enemies,
2048 turns, no ogres/travel, +0.002 first-seen floor reward, -0.001 turn cost,
15x15 wall-blocked vision and LOS-gated waking.

Select clumped placement independently with probability 1/3 at every reset.
This is a fraction of episodes, not necessarily a fraction of training turns.
Ordinary placement remains unchanged in the other episodes. The original
regular-enemy spawn rule excludes the player's tile, without a minimum distance.
Preserve that rule. No placement label is exposed to the model.

For a clumped episode, first generate normal positions, stats and energy, then
relocate the 24 enemies into eight triples using a separate copy of the RNG.
Each anchor is uniformly selected among currently empty floor tiles with two
eligible neighbors. Select two distinct neighboring floor tiles uniformly
without replacement, excluding the player and previously placed enemies.
Different triples may touch. Stats, energy, sleep and gameplay RNG are preserved;
initial vision/discovery is calculated after relocation. Clumping does not make
enemies wake as a group: normal individual LOS/wake rules apply.

## Validation and evaluation

Before training, check 4,096 initial worlds across all 256 training layouts for
each mode (ordinary, one-third mix, all clumped): valid distinct tiles, player
exclusion, triple geometry, original HP/energy and sleeping state. Check the mix
frequency is between 30% and 37%. Check ordinary-mode observations, masks and
step outputs exactly match the previous simulator for 64 worlds x 128 steps.
The added internal placement flag changes state size, so compare behavior rather
than raw state bytes against the old simulator.

Training checkpoints evaluate on ordinary validation placement. After training,
evaluate the existing ordinary-trained 30M policy and the mixed-trained 30M policy
on both ordinary and fully clumped placement: 1,024 sampled episodes per cell,
32 held-out validation layouts x 32 episodes, seed 900000. Test layouts untouched.
Retain separate labels for each training/evaluation combination.

Report clears/deaths/timeouts, mean turns/kills, single/multi-enemy contact,
fatal crowding, walls and retreat opportunities. Reuse the read-only wall/death
probe, with original fatal-action replay and 128-step state/observation/output
parity checks. Ordinary evaluation must reproduce each stored training result.
Clumped evaluation is a new distribution, so it has no prior outcome reference.
Geometry and one-turn survival do not establish eventual escape.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-clumps-v1/scripts/run_experiment.py
```

Artifacts: `results/vision15-clumps-preflight.json`,
`results/vision15-clumps-30m.json`, `results/vision15-clumps-evaluation.json`.
Training time excludes evaluation/setup/I/O; the launcher records total wall time.
Checkpoints are bounded to a 2 GiB suite with a 5 GiB free-space reserve. Existing
ignore rules cover builds, checkpoints and logs. This is a one-seed exploratory
screen; better ordinary validation is the main evidence for useful transfer.

## Completed results

Both policies reached 30,015,488 decisions. Sampled evaluation:

| Training | Evaluation placement | Clear | Death | Timeout | Mean turns | Mean kills | Multi-adjacent share of contact turns |
|---|---|---:|---:|---:|---:|---:|---:|
| ordinary | ordinary | 78.71% | 20.41% | 0.88% | 543.0 | 21.01 | 19.87% |
| ordinary | clumped | 59.86% | 39.55% | 0.59% | 439.9 | 18.31 | 24.94% |
| mixed | ordinary | 78.03% | 21.19% | 0.78% | 528.9 | 20.89 | 19.98% |
| mixed | clumped | 62.99% | 36.33% | 0.68% | 444.4 | 18.88 | 22.92% |

Mixed training gained 3.125 percentage points (32/1024 episodes) on clumped
validation and lost 0.684 points (7/1024) on ordinary validation. This is modest
adaptation to clumped placement, without demonstrated ordinary-layout benefit.
A single training seed does not establish a reliable advantage.

The original policy's multi-enemy share of adjacency-contact turns increases
from 19.87% to 24.94% under clumped evaluation. For the mixed policy, clumped
contact is 22.92%. This is consistent with less crowding, but is not evidence
by itself of learned retreat: policies visit different states and deaths change
which turns are counted. Clumping also changes spatial search/discovery patterns.

In fatal episodes' last 50 turns, crowding-reducing moves were taken on 31.6%
of eligible low-HP turns for ordinary training/ordinary evaluation, versus 35.6%
for mixed training/ordinary evaluation. On clumped evaluation these are 26.7%
and 29.9%. These death-conditioned, local measures cannot establish escape skill.

Initial weights match the original seed-0 initialization exactly. All placement,
ordinary-behavior parity, diagnostic parity, geometry and original fatal-action
replay checks passed. Both ordinary-evaluation results reproduce their stored
training outcomes exactly. Test layouts remain untouched.

Mixed training took 267.63 seconds, versus 220.03 cumulative
seconds for the original run. Entire new experiment including preflight, setup,
evaluations and I/O took 524.30 seconds (8.74 minutes).
Training suite storage was 38.9 MiB; comparison checkpoints were reused.
