# Six enemies, three-step hallway retreat

2026-09-16. Follow-up to the [one-step hallway test](../hallway/README.md),
evaluating the same original and clump-trained seed-0 30M policies without training.

```text
ggg
ggg
...
.@.
...
x.x
x.x
xxx
```

Missing tiles are walls. All 17 local floor tiles are initially seen, and all
six enemies are visible and awake. Relative to the player, rows -3/-2 contain
enemies, rows -1/0/1 are open, and rows 2/3 have only the central floor tile.
Three straight moves reach the end of the corridor. The first corridor tile
still permits diagonal adjacency from three room tiles; the last permits only
one adjacent enemy. Native assertions check the retreat path, no initial
adjacent enemies, and exactly one floor neighbor at the destination.

## Protocol

Four rotations, player HP 6/12/18, 512 combat RNG seeds per condition. As in the
previous diagnostic, use turn 256/2048, unchanged player defenses, regeneration,
combat and observations, and sampled policy actions. Now 18 required enemies
have already been defeated and six remain. The extra progress input is 17/1024.
A 256-action evaluation cap resolved every rollout. Invisible, unreachable
padding permits normal terminal auto-reset; it contains no test enemies.
Native ray definitions generate LOS; initial observation assertions check six
visible enemies, all nine actions available, and the seen-floor count.

The larger groups use existing mixed rosters, not six copies of the previous
single enemy type:

| Group | Front row, left to right (native kinds) | Back row | HP | Speeds | Damage proxies |
|---|---|---|---|---|---|
| Weaker | 0, 1, 2 | 0, 1, 2 | 8, 10, 12 repeated | 10, 10, 10 repeated | 3, 3, 1 repeated |
| Tougher | 3, 4, 5 | 3, 4, 5 | 16, 12, 10 repeated | 10, 12, 14 repeated | 5, 5, 3 repeated |

Each row rotates with the geometry. Enemy energies start at 70..79, all awake.
The change in roster means comparing against the earlier three-enemy test does
not isolate geometry alone. Within this test both policies receive identical
scenarios. Combat RNG seeds are shared across rotations and arms, so rotations
are not independent random samples. Policy RNG seed is 900000.

Controls hold position and attack the lowest-HP adjacent enemy (wait otherwise),
or take three straight retreat steps and then use that same fighting rule.
Additional policy arms force only the first retreat step, or all three steps,
then restore model control. Arrival at the final corridor tile and attacks before
first arrival are recorded. Initial probability of straight retreat and of any
of the three moves away from the enemies are separate measures.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/hallway-six/run.py
```

## Results

Wins, equally averaged across rotations:

| Enemies | HP | Hold/fight | Retreat 3/fight | Original policy | Clump-trained policy |
|---|---:|---:|---:|---:|---:|
| Weaker | 6 | 63.7% | 99.4% | 32.9% | 75.4% |
| Weaker | 12 | 95.4% | 100% | 68.0% | 89.3% |
| Weaker | 18 | 99.9% | 100% | 88.6% | 94.9% |
| Tougher | 6 | 0.2% | 47.4% | 2.6% | 21.3% |
| Tougher | 12 | 2.0% | 85.3% | 7.4% | 51.8% |
| Tougher | 18 | 10.2% | 95.4% | 15.2% | 72.2% |

Tougher enemies, HP 12:

| Intervention | Original wins | Clump-trained wins |
|---|---:|---:|
| Natural policy | 7.4% | 51.8% |
| Force first retreat step, then policy | 53.8% | 74.1% |
| Force three retreat steps, then policy | 85.2% | 85.2% |

Natural-policy arrival at the protected square is 11.4% original versus 74.0%
clump-trained. The original attacks before reaching it in 97.9% of episodes,
versus 72.9% for clump-trained. Arrival alone does not guarantee winning: it can
be too late or the policy can subsequently leave. Forcing the route does not
prove a model's intended plan, but it demonstrates a large benefit from getting
to that position before committing to combat.

Win rates across the four rotations at HP 12/tougher enemies:

| Retreat direction | Original | Clump-trained |
|---|---:|---:|
| South, as drawn | 8.6% | 49.2% |
| West | 2.0% | 59.2% |
| North | 6.2% | 35.9% |
| East | 12.9% | 62.9% |

Unlike the adjacent hallway test, this task shows a large advantage for the
clump-trained checkpoint across every health/roster group. Neither reliably
reaches the control's performance. Both can fight effectively once the three
steps are supplied, which suggests a major weakness in initiating/completing
useful positioning. This is a synthetic local test with a very small seen-floor
count, one training seed, and two particular rosters; it does not establish
broad generalization or isolate the learned mechanism.

All observations, layout and path assertions passed; there were no unresolved
rollouts. Runtime was about 14 seconds including compilation and map generation.
Full per-condition outcomes, first-action probabilities, position diagnostics,
checkpoint and source hashes: `results/hallway-six-retreat.json`. Maps/libraries
are regenerated inside ignored `build/`. Existing experiments are unchanged.
