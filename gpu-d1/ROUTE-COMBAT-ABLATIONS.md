# Separate combat ablations, 30M decisions each

Each run starts from scratch with seed 0 and the corrected route-cue setup:
256 training layouts, 40 enemies, sleep on, 1024-turn episodes, primitive9
actions, remembered 11x11 ring, known-frontier pointer and route direction.
Validation uses the same 32 held-out layouts with 32 episodes each, with
sampled and greedy actions. The untouched 100-map test split remains reserved.

| Variant | Only experimental change | Observation size |
| --- | --- | --- |
| `route_awake` | Append one awake bit per living monster slot; dead/unused slots zero | 461 |
| `route_stack4` | Concatenate four consecutive observations, oldest first | 1684 |
| `route_death5` | Death reward becomes -5 instead of -1 | 421 |

The awake variant uses the simulator's awake state for all living monster
slots, consistent with the existing global monster-position inputs. This is
an additional state input, not an inference from visibility.

History duplicates the initial observation four times at reset. Auto-reset
erases the previous episode's history separately for each world. It includes
no previous actions or rewards. Hidden layers remain 128 units, so the larger
input increases parameter count; a gain would not isolate memory from model
capacity. Checkpoints retain history and restore the underlying current
observation for exact resumption.

All runs retain +1 per kill, +3 for clearing, -0.001 per turn, and +0.002 per
newly seen floor tile. Compare clears, deaths, timeouts and kills, rather than
raw returns across different death penalties. These are three separate runs,
not cumulative changes, at 30M each (90M total, rounded to full PPO updates).

The existing corrected `route_cue` seed-0 control at 30M had 53.6133% sampled
clears and 45.4102% deaths, with 583.52 seconds of training. Its output is in
`learning-runs/ring-route-cue-corrected-100m`. Compare at equal training
decisions and report training seconds too. One seed is a screening test;
replicate promising changes before declaring a reliable improvement.

```sh
gpu-d1/.venv/bin/python -u gpu-d1/scripts/run_ring_ablations.py \
  --variants route_awake,route_stack4,route_death5 --seeds 0 \
  --steps 30000000 --output gpu-d1/learning-runs/route-combat-ablations-30m
```

The suite runs sequentially and reports validation at 0, 1M, 3M, 10M and
30M. Training time excludes evaluation, compilation and checkpoint writes.
It retains latest and best checkpoints per variant, using the existing 2 GiB
suite limit and 5 GiB free-space reserve. Repeating the command resumes
interrupted jobs and skips completed jobs.

Verification: all four smoke variants (control plus three changes), explicit
awake/dead and death-reward checks, route-direction semantic fixtures,
history/reset checks, storage tests, and exact interrupted-resume comparison
for the history variant.

## Queued exploration-reward ablation

`route_no_explore` is an additional independent seed-0 run to 30M, starting
after the three runs above finish successfully. It uses the original corrected
route-cue inputs (421 values), no history or awake bits, and death penalty -1.
Only the newly seen floor reward changes from +0.002 to zero. Seen/viewed
memory, frontier computation and route cues remain enabled. Compare its
clears, deaths, timeouts and learning curve against the existing route-cue
control; raw reward totals are not comparable across reward definitions.

```sh
gpu-d1/.venv/bin/python -u gpu-d1/scripts/run_route_no_explore.py \
  --after-suite gpu-d1/learning-runs/route-combat-ablations-30m \
  --steps 30000000 --seeds 0 \
  --output gpu-d1/learning-runs/route-no-explore-30m
```

The queue waits on the preceding suite's lock without consuming GPU time.
If that suite exits unfinished, the queue stops rather than racing a resume.
This separate entry point preserves the running suite's source hashes.
It uses the same evaluations, timing reports and disk limits as the other runs.

## Completed 30M screen

All results below use seed 0 and the same 32 validation maps × 32 episodes.
Times cover training only, excluding evaluation and setup.

| Configuration | Sampled clears | Sampled deaths | Greedy clears | Training minutes |
| --- | ---: | ---: | ---: | ---: |
| Original corrected route | 53.61% | 45.41% | 17.29% | 9.73 |
| Awake inputs | 51.37% | 47.46% | 39.06% | 9.95 |
| Four-frame history | 42.19% | 56.45% | 32.91% | 10.64 |
| Death penalty -5 | 50.78% | 48.14% | 19.04% | 9.62 |
| Exploration reward zero | 39.75% | 59.47% | 16.60% | 9.88 |

No variant improved sampled clears in this seed. Awake inputs and history
improved greedy clears, but this does not establish why. Removing exploration
reward reduced sampled clears by 13.87 percentage points and raised deaths by
14.06 points; timeouts remained below 1%. This supports retaining the bonus
for now, without establishing the behavioral mechanism or a multi-seed effect.
At 10M the no-exploration run was near the control (32.91% versus 33.20% clears),
so judging only the early checkpoint would have missed the later difference.

## Scaled clear bonus follow-up

Fresh `route_clear_scaled`, seed 0, 30M: terminal clear bonus is
`0.25 * initial enemy count`, i.e. +10 at 40 enemies, +6 at 24, +2 at 8.
`Config.count` is fixed throughout the episode; the bonus is not based on
remaining enemies. All other settings match the original corrected route,
including +0.002 exploration reward and -1 death penalty. At fixed 40 enemies
this tests +3 versus +10, not generalization across enemy counts.

```sh
gpu-d1/.venv/bin/python -u gpu-d1/scripts/run_ring_ablations.py \
  --variants route_clear_scaled --seeds 0 --steps 30000000 \
  --output gpu-d1/learning-runs/route-clear-scaled-30m
```

Semantic checks cover the bonus at 8, 24 and 40 initial enemies and reset;
an end-to-end smoke run checks compilation, training, evaluation and saving.
