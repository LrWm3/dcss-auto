# Waiting while defending: hallway versus diagonal pocket

2026-09-16. Extend both existing hallway diagnostics with the same read-only
counter used for the distant pocket: turns at the protected destination with
at least one live adjacent enemy, and whether the chosen action attacks or waits.
Reevaluate the same checkpoints/scenarios/RNG. Every previously recorded arm
metric, including outcome rates and first-action probabilities, reproduced
exactly. No training or behavioral intervention was added beyond the original
arms. Results now retain per-condition contact/attack/wait turn counts and
`pre_instrumentation_metrics_exact=true`.

Compare tougher enemies at 12/18 player HP, summing contact turns across the
four rotations before dividing. These are fractions of qualifying turns, not
fractions of episodes. They exclude waiting when no enemy is adjacent.

## Full retreat supplied, then unmodified policy

| Scenario | Original wait fraction | Clump-trained wait fraction |
|---|---:|---:|
| One-step hallway, three enemies | 0.0216% | 0.0020% |
| Three-step hallway, six enemies | 0.1542% | 0.0100% |
| Four-step diagonal pocket, six enemies | 36.83% | 36.28% |
| Six-step diagonal pocket, six enemies | 34.55% | 38.76% |

The six-enemy rows share rosters and initial health. Three-enemy hallway uses the
previous homogeneous tougher enemy type, so it is contextual rather than the
closest controlled comparison. Each geometry changes more than a single feature;
the data do not isolate orientation, local wall pattern, observation history or
other input differences. The model chooses attacks on essentially every hallway
contact turn, but often waits in the distant diagonal pocket.

## Natural policy, conditional on reaching the protected square

| Scenario | Original wait fraction | Clump-trained wait fraction |
|---|---:|---:|
| One-step hallway, three enemies | 0.0264% | 0.0020% |
| Three-step hallway, six enemies | 0.1160% | 0.0114% |
| Four-step diagonal pocket, six enemies | 33.16% | 25.89% |
| Six-step diagonal pocket, six enemies | 39.45% | 7.38% |

Natural arrival selects different fights/states, especially in the original
six-step case where very few episodes arrive. Full-retreat arms offer the
clearer comparison. These measurements establish a substantial geometry-dependent
behavior difference, not a general tendency to wait whenever defending. Why
those observations produce waiting has not been isolated.

Reproduction:

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/hallway/run.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/hallway-six/run.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/distant-pocket/run.py --distance 4
gpu-d1/.venv/bin/python gpu-d1/diagnostics/distant-pocket/run.py --distance 6
```

Artifacts: `results/hallway-retreat.json`, `results/hallway-six-retreat.json`,
`results/distant-pocket-4-retreat.json`, `results/distant-pocket-6-retreat.json`.
Hallway keys are `protected_contact_turns`, `protected_attack_turns`,
`protected_wait_turns`; pocket keys use the `pocket_` prefix. Each array is mean
turn count per condition; equal rollout counts permit summing across rotations.
