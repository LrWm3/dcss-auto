# Pocket rotation and reflection: waiting during defense

2026-09-16. Test all eight square symmetries of the 4- and 6-step distant-pocket
scenarios: reflect x if requested, then rotate clockwise 0/90/180/270 degrees.
Transform the room, target, enemy positions and their type assignments together.
Keep player at the same absolute map coordinate. Reflecting changes which room
corner holds the pocket without changing the starting player/enemy distances.

Use the original and clump-trained seed-0 30M checkpoints, the existing health
and roster sweep (6/12/18 HP, weaker/tougher six-enemy groups), 512 combat RNG
seeds per condition, and sampled actions with seed 900000. Force the entire
retreat route, then return control to the policy. Also retain the scripted
retreat-and-fight controller. No training or input changes.

The main measure is pooled wait actions divided by contact turns at the protected
square with an adjacent enemy. This excludes waiting for enemies to arrive.
Rotations share combat seeds and are not independent RNG replicates. Initial
LOS, observed target tile, path and one-neighbor geometry are asserted in every
transformation. Unreflected reruns reproduce every previous corresponding arm
metric exactly, including outcomes and action counters.

```sh
# Run each combination: distance 4/6, mirror 0/1.
gpu-d1/.venv/bin/python gpu-d1/diagnostics/pocket-symmetry/run.py --distance 6 --mirror 1
```

## Findings

At tougher enemies / 12 HP, waiting changes dramatically with pocket direction.
Mirroring while comparing the same compass direction barely changes it. The
original policy waits most with the pocket northwest (enemy approaches from
southeast), while the clump-trained policy waits most with the pocket northeast
(enemy approaches from southwest). The scripted fight controller never waits
on an adjacent-enemy contact turn in any of these cases.

This points to a strong direction-specific policy behavior rather than a general
preference to wait in protected terrain. The exact cause is not isolated:
geometry, policy input/action asymmetry and deterministic simulator tie-breaks
can all contribute. Paired reflection does not guarantee identical subsequent
combat states, because native movement/attack tie-breaks are not rotated.
The effect is consistent at both tested pocket distances, but the headline
numbers below concern a particular roster and health, not all states.

Artifact names: `results/pocket-symmetry-{4,6}-mirror{0,1}.json`. These retain
all health/roster/rotation conditions, contact/attack/wait counts, outcome and
unresolved rates, input checks and source/checkpoint hashes. Generated maps and
libraries remain under ignored `build/`. Previous experiments are unchanged.

## 4-step pocket: tougher group, HP 12

| Pocket direction | Original wait | Original mirrored wait | Clump-trained wait | Clump-trained mirrored wait |
|---|---:|---:|---:|---:|
| SE | 28.93% | 29.28% | 11.37% | 11.13% |
| SW | 11.52% | 11.42% | 8.90% | 8.66% |
| NW | 69.89% | 70.25% | 0.64% | 0.73% |
| NE | 10.78% | 10.34% | 77.68% | 76.73% |

Unreflected survival rates in the same order (SE/SW/NW/NE):

- ordinary_force_route: 70.3%, 78.1%, 17.6%, 79.1%.
- mixed_force_route: 80.1%, 79.7%, 82.6%, 19.5%.

## 6-step pocket: tougher group, HP 12

| Pocket direction | Original wait | Original mirrored wait | Clump-trained wait | Clump-trained mirrored wait |
|---|---:|---:|---:|---:|
| SE | 41.47% | 42.20% | 3.79% | 3.60% |
| SW | 2.31% | 2.52% | 4.76% | 4.84% |
| NW | 63.32% | 63.00% | 0.89% | 0.95% |
| NE | 5.94% | 6.11% | 84.52% | 84.24% |

Unreflected survival rates in the same order (SE/SW/NW/NE):

- ordinary_force_route: 62.1%, 83.6%, 28.1%, 80.5%.
- mixed_force_route: 82.0%, 80.9%, 83.6%, 7.4%.
