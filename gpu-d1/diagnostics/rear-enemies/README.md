# Do visible enemies behind the adjacent enemy increase waiting?

Yes, often substantially, but not universally and not as the sole explanation.
This test directly changes enemy information in a frozen policy observation;
it does not infer the effect from different combat trajectories.

## Protocol

Use all six original unaugmented 30M policies: ordinary and one-third-clumped
training for seeds 0, 1, 2. Reproduce the existing six-step diagonal pocket
forced-route rollouts, 24 roster/HP/orientation conditions x 512 combat seeds,
256-action diagnostic cap. Analyze only tough-roster, initial player HP 12/18,
all four rotations. Supply the first six diagonal retreat actions, then use the
unchanged sampled policy with the complete original observation.

On each active turn when the player is in the protected pocket with exactly one
adjacent enemy, query three observations without sampling or changing the world:

1. The original full observation.
2. Zero nonadjacent visible enemies in BOTH the 15x15 enemy grid and all 40 enemy
   records. Preserve the adjacent enemy's exact record and original slot.
3. As a secondary encoding control, move that surviving record to slot 0 after
   removing the others. The primary comparison does not change its slot.

Keep terrain, LOS visibility, remembered ring, frontier/route cues, player HP,
time, absolute coordinates, coverage, and action mask fixed. All actual rollout
actions use the original full observation. Assert matched enemy-grid/record counts,
exactly one retained adjacent enemy, and unchanged non-enemy features. With no
rear enemies visible, intervention #2 must leave the entire input identical and
produce the same wait probability within floating-point tolerance.

Win, death and unresolved results reproduce every stored reference condition
exactly for every model. Additional policy queries do not consume RNG. Reports
include first-contact observations (one per episode), all contact states,
with/without rear enemies, and high-wait (probability >= .5) states.

## Main results

Mean wait probability on the SAME captured contact states with at least one
additional visible nonadjacent enemy. Use the repeatedly troublesome NW pocket
for ordinary and NE pocket for clumped models. These are state/turn-weighted
means, not independent episode samples or new rollout wait rates.

| Training seed | Ordinary NW: full → adjacent only | Clumped NE: full → adjacent only |
|---|---:|---:|
| 0 | 64.64% → 48.49% | 85.10% → 52.13% |
| 1 | 92.31% → 3.56% | 69.68% → 39.84% |
| 2 | 34.86% → 24.67% | 49.97% → 43.55% |

Each row/orientation includes contact states from all 512 episodes. The extra
enemies materially increase the action probability of waiting, particularly for
ordinary seed 1. Their removal does not eliminate waiting for most other models.

To avoid weighting episodes by how long they wait, the first contact alone gives:

| Training seed | Ordinary NW: full → adjacent only | Clumped NE: full → adjacent only |
|---|---:|---:|
| 0 | 72.83% → 49.21% | 87.24% → 69.49% |
| 1 | 95.38% → 1.29% | 80.27% → 40.35% |
| 2 | 48.88% → 35.86% | 31.62% → 47.86% |

All first-contact states have five visible rear enemies. Clumped seed 2 is an
explicit counterexample to 'rear enemies always cause more waiting': hiding them
increases waiting at first contact, although it decreases the contact-time-weighted
average later. The policy response depends on the particular state.

## Secondary slot-order observation

After hiding rear enemies, placing the adjacent enemy's record in slot 0 changes
its wait probability too. Clumped seed 0 NE: 52.13% → 35.40%; seed 1 NE:
39.84% → 23.70%; seed 2 NE: 43.55% → 43.48%, across the same with-rear states.
This demonstrates sensitivity to enemy-record placement in addition to the
rear-enemy information; it is not part of the primary removal comparison.

The direct input intervention establishes an effect on policy action probabilities,
not that the model reasons correctly/incorrectly about crowding, nor that hiding
rear enemies would improve episode survival. No counterfactual actions are executed.
Only visible nonadjacent enemies are removed from the observation; hidden enemies
have no records/grids to remove. Current HP and enemy identity may differ from the
earlier constructed single-enemy test, so its percentages are not interchangeable.

Run:

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/rear-enemies/run.py
```

Full results: `gpu-d1/results/rear-enemy-wait-intervention.json`.
Runtime was 16.53 seconds including compilation and map construction. No training.
