# Larger room, farther visible diagonal pocket

2026-09-16. Follow-up to the [two-step diagonal pocket](../diagonal-pocket/README.md).
No training. Same original and clump-trained seed-0 30M policies, six-enemy
weaker/tougher rosters, HP 6/12/18, four rotations, and 512 combat RNG seeds per
condition. Enemies stay at their original offsets: three at y=-2 and three at
y=-3, x=-1/0/1. Player starts at (0,0), turn 256/2048, with 18 enemies defeated.

For pocket distance d, room floor is x=-(d-1)..d-1, y=-3..d-1, plus pocket
(d,d). All other local tiles are walls. The two cardinal tiles beside the pocket
are blocked; its sole floor neighbor is diagonal. Expand d from 2 to 4 and 6.
This changes room size and route length together, not distance in isolation.
There are 16, 50 and 100 visible floor tiles respectively, which also changes
the existing seen-floor observation scalar. Distant disconnected padding is
inaccessible and invisible, used only by normal terminal auto-reset.

Native checks assert path walkability, one pocket neighbor, corner blockers and
actual initial LOS to the pocket. Python checks the target's terrain and current
visibility observation channels in every rotation, all six visible enemies and
all local floor seen. Both new pockets are within the 15x15 observation window;
this is not a hidden-target test.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/distant-pocket/run.py --distance 4
gpu-d1/.venv/bin/python gpu-d1/diagnostics/distant-pocket/run.py --distance 6
```

Controls: stay/fight or immediately follow the diagonal route then hold/fight.
Model interventions supply the first step or the entire route, then hand back
control. Policy steps are sampled with seed 900000. The diagnostic cap remains
256 actions; unresolved episodes are reported separately, not counted as wins
or deaths. Combat seeds are shared across rotations and arms, so rotations are
not independent RNG replicates. All comparisons are among these fixed checkpoints.

Track arrival, departures after arrival, and actions while in the pocket with
an adjacent enemy. Waits in that last category cannot be explained simply by
waiting for an enemy to arrive. Diagnostic counters do not alter observations,
actions or simulation. Early runs were repeated to add those counters; the
artifacts below contain the final instrumented evaluations.

## Interpretation

Both policies lose performance as the room expands and the visible pocket moves
farther away. Clump-trained remains better on average, but neither reliably
reaches the protected position. Immediate retreat-and-hold survival remains
around 83% for the tougher group at HP 12, so the larger loss is not explained
by the route becoming physically ineffective.

Even with the full route supplied, learned policies underperform the hold/fight
controller. Neither leaves the pocket in the HP-12/tougher comparisons. Instead,
they often wait while an enemy is adjacent. After the six-step forced route,
waits are 34.5% of such turns for original and 38.8% for clump-trained, versus
zero for the fight controller. This exposes a separate combat-action weakness,
not just inability to navigate to the pocket. Direction and surrounding geometry
can still influence the policy even after it reaches the one-enemy position.

This is a synthetic scenario family, not an estimate of ordinary-map performance
or a proof about general planning ability. Pocket motif novelty was separately
checked in the previous experiment and cannot be assumed here.

## Artifacts

`results/distant-pocket-4-retreat.json` and `results/distant-pocket-6-retreat.json`
contain all conditions, outcomes, cap-unresolved rates, arrival/departure/action
counters, initial action probabilities and source/checkpoint hashes. The earlier
2-step comparison is reused from `results/diagonal-pocket-retreat.json`.
Generated maps/libraries are ignored under `build/`; existing runs are unchanged.

## Results: tougher enemies, player HP 12

| Pocket steps | Original wins | Clump-trained wins | Retreat then hold/fight wins | Original arrival | Clump-trained arrival |
|---|---:|---:|---:|---:|---:|
| 2 | 35.0% | 56.4% | 82.6% | 53.1% | 78.9% |
| 4 | 17.5% | 30.6% | 82.3% | 33.0% | 51.2% |
| 6 | 6.0% | 19.3% | 83.0% | 11.5% | 27.4% |

| Pocket steps | Original, full route forced | Clump-trained, full route forced |
|---|---:|---:|
| 2 | 79.2% | 80.8% |
| 4 | 61.3% | 65.5% |
| 6 | 63.6% | 63.5% |

## Full natural-policy sweep

| Distance | Roster | HP | Original wins | Clump-trained wins | Retreat/hold control wins |
|---|---|---:|---:|---:|---:|
| 4 | Weaker | 6 | 47.5% | 73.3% | 98.7% |
| 4 | Weaker | 12 | 76.5% | 93.9% | 100.0% |
| 4 | Weaker | 18 | 91.0% | 98.4% | 100.0% |
| 4 | Tougher | 6 | 6.3% | 11.6% | 47.2% |
| 4 | Tougher | 12 | 17.5% | 30.6% | 82.3% |
| 4 | Tougher | 18 | 26.5% | 48.0% | 95.5% |

Distance 4 evaluation runtime: 17.6 seconds including map generation and compilation.
| 6 | Weaker | 6 | 30.2% | 49.3% | 99.2% |
| 6 | Weaker | 12 | 67.9% | 76.0% | 100.0% |
| 6 | Weaker | 18 | 89.5% | 92.8% | 100.0% |
| 6 | Tougher | 6 | 1.3% | 9.8% | 48.5% |
| 6 | Tougher | 12 | 6.0% | 19.3% | 83.0% |
| 6 | Tougher | 18 | 10.7% | 23.8% | 94.5% |

Distance 6 evaluation runtime: 18.1 seconds including map generation and compilation.

All natural-policy HP-12/tougher trials resolved by the cap. In the six-step
full-route-forced clump-trained arm, 0.15% remained unresolved; these are not
counted as deaths. Per-condition cap outcomes for the full sweep are in JSON.
