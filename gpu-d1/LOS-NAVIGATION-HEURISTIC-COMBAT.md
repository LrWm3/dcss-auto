# Learned LOS navigation with heuristic encounters

Frozen rest/sleep seed-0 model after 10027008 training decisions. No retraining. Same 1,024 starting validation episodes (32 layouts × 32 placements), 24 ordinary enemies, 15×15 wall-blocked LOS, LOS-gated waking, and 2,048 policy decisions. Rest may consume multiple physical turns.

## Ownership rules

- Learned-only: original model chooses every action.
- Awake-trigger hybrid: start heuristic ownership when at least one **visible awake** enemy exists; keep ownership until **no enemy is visible**, including sleepers.
- Visible-trigger hybrid: start ownership at any visible enemy, including sleeping enemies; end when no enemy is visible.
- While engaged, use the LOS-only seek-and-destroy + hallway retreat + awake-enemy waiting policy. It attacks adjacent enemies, waits for awake enemies when none is adjacent, and may retreat to the original strict known-hallway targets. Sleeping-only enemies may be approached.
- Outside encounters, the learned policy controls everything, including whether to rest. There is no extra forced healing rule.
- The heuristic remembers observed terrain during learned navigation. Retreat cannot secretly initiate while the model owns control. When enemies leave sight, the retreat state resets.
- Heuristic-only: the same encounter policy also handles exploration and rest.
- No native privileged enemy-location pursuit is used in any arm. All policies receive the original LOS observation and action mask.

Sampled and greedy refer only to model decisions. Sampling continues across the full batch on each decision, including overridden actions, matching the original evaluation RNG consumption convention. Simulator RNG and initial states are matched; later trajectories and combat RNG consumption can diverge.

## Results

| Policy | Clears | Deaths | Timeouts | Mean physical turns | Clear-only turns |
|---|---:|---:|---:|---:|---:|
| learned-sampled | 867 (84.67%) | 148 | 9 | 625.3 | 686.2 |
| learned-greedy | 609 (59.47%) | 288 | 127 | 898.8 | 849.9 |
| awake-sampled | 991 (96.78%) | 18 | 15 | 709.1 | 699.6 |
| visible-sampled | 1001 (97.75%) | 22 | 1 | 686.4 | 698.9 |
| awake-greedy | 887 (86.62%) | 17 | 120 | 964.9 | 826.7 |
| visible-greedy | 898 (87.70%) | 21 | 105 | 944.9 | 831.0 |
| heuristic-none | 993 (96.97%) | 23 | 8 | 682.6 | 686.1 |

| Hybrid | Mean model decisions | Mean heuristic decisions | Mean encounters | Mean rest uses |
|---|---:|---:|---:|---:|
| awake-sampled | 419.1 | 213.0 | 20.7 | 8.3 |
| visible-sampled | 386.4 | 223.9 | 22.2 | 8.2 |
| awake-greedy | 681.9 | 208.0 | 20.0 | 8.1 |
| visible-greedy | 642.0 | 229.3 | 34.2 | 8.0 |

## Paired outcomes versus the corresponding learned-only policy

| Hybrid | Newly clear | Previously clear, now fails |
|---|---:|---:|
| awake-sampled | 146 | 22 |
| visible-sampled | 148 | 14 |
| awake-greedy | 326 | 48 |
| visible-greedy | 341 | 52 |

## Validation and limits

Both learned-only controls exactly reproduce saved sampled/greedy clear rate, death rate, timeout rate, kills and physical turns. Heuristic-only exactly reproduces the prior LOS-only waiting/retreat result on the same metrics. All selected actions pass the original mask; all episodes terminate. Encounter-gate checks cover awake versus sleeping triggers, persistence while sleepers remain, reset with no visible enemies, and inactive worlds. Checkpoint, policy sources and simulator library hashes are recorded in the raw artifact.

These are evaluation-time interventions on one frozen model and a reused validation panel. The comparison tests whether replacing its encounter decisions helps; it does not measure the performance of a model trained specifically for navigation with heuristic combat. A change in clear rate cannot be attributed to attacks alone: retreat, waiting, target selection, pursuit of sleepers and the states handed back to navigation change together.

Evaluation wall seconds (all seven arms): 100.0. No training time incurred.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/run_hybrid.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/report_hybrid.py
```

Raw artifact: `results/los-navigation-heuristic-combat.json`.
