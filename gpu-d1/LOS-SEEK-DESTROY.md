# LOS-only frontier + seek-and-destroy baseline

2026-09-16. Implemented and evaluated without training. Uses only observation tensors, legal-action masks, and terrain remembered from previous observations. The CUDA policy API has no simulator-state pointer, true-map pointer, hidden-enemy list, or precomputed full-map path distances.

## Policy

1. Optional rest variant: rest whenever the original environment permits it (below full HP, no visible enemy, including sleepers).
2. Attack the lowest-HP **visible adjacent** enemy.
3. Otherwise, follow a shortest path through **observed floor only** toward the nearest reachable **currently visible** enemy.
4. With no reachable visible enemy, follow the existing nearest-known-frontier route cue available to the learned model. At an anchor, probe its supplied first unknown neighbor.
5. If no target or frontier route exists, wait.

Movement is one primitive step per decision, not a travel macro. Rest keeps its original macro semantics. Terrain memory persists during an episode; enemy locations are not retained when hidden. No hidden enemy count or location is used to choose actions. The policy has explicit remembered terrain and BFS computation, which is a stronger algorithmic structure than the learned MLP; it does not have privileged environment information.

Frontier selection/ties reuse the original audited observed-terrain helper. Visible-enemy path lengths use a separate BFS over the policy’s own observed-floor memory. Adjacent attack ties use fixed compass order; equally distant visible targets use observation encounter-slot order.

## Results

Same 1,024 validation episodes (32 maps × 32 placements), 24 enemies, original branch libraries and deadlines. Learned columns are saved final sampled evaluations; both heuristic columns are newly evaluated baselines.

| Configuration | Budget | Learned clear % | LOS-only heuristic clear % | Privileged heuristic clear % |
|---|---|---:|---:|---:|
| 9×9 LOS, baseline (30M) | 512 turns | 16.41 | 25.88 | 88.57 |
| 15×15 LOS, baseline (10M) | 2048 turns | 61.52 | 90.04 | 88.67 |
| 15×15 LOS, seen count / death −4 (30M) | 2048 turns | 78.71 | 90.04 | 88.67 |
| 15×15 LOS, sleep / wait (10M) | 2048 decisions | 80.37 | 90.04 | 88.67 |
| 15×15 LOS, sleep / rest (10M) | 2048 decisions | 84.67 | 92.68 | 93.55 |

Rest-enabled row uses rest for both heuristics. The other rows use no rest. The 2048-decision budget can allow more than 2048 physical turns in the rest-enabled experiment. The same plain LOS-only heuristic gives identical outcomes across all four 15×15 branches, including the rest-enabled branch when rest is not chosen.

| Configuration | LOS-only death % | LOS-only timeout % | LOS-only mean physical turns | Privileged mean physical turns |
|---|---:|---:|---:|---:|
| 9×9 LOS, baseline (30M) | 9.08 | 65.04 | 460.2 | 325.1 |
| 15×15 LOS, baseline (10M) | 9.28 | 0.68 | 504.9 | 325.1 |
| 15×15 LOS, seen count / death −4 (30M) | 9.28 | 0.68 | 504.9 | 325.1 |
| 15×15 LOS, sleep / wait (10M) | 9.28 | 0.68 | 504.9 | 325.1 |
| 15×15 LOS, sleep / rest (10M) | 6.54 | 0.78 | 609.3 | 426.2 |

Mean turns includes deaths and clears. Among successful clears only, the 15×15 no-rest heuristic takes 533.0 turns versus 352.1 privileged; with rest, 630.5 versus 447.7. Finding enemies therefore adds substantial time even though final completion rates are close.

The 15×15 no-rest policy averages 138.6 adjacent attacks, 40.4 pursuit steps toward visible enemies, 323.3 frontier steps, and 2.6 idle waits per episode. The rest version averages 7.89 rest uses and 94.3 physical resting turns.

## What this establishes

Hidden map/enemy knowledge is not necessary to attain approximately 90% clear rate in the 15×15, long-budget toy environment: explicit exploration, known-terrain pathfinding and immediate attack rules suffice. The recent learned sleep-status policies still trail this nonprivileged baseline by 9.67 points without rest and 8.01 points with rest. This comparison implicates learned action selection and navigation rather than requiring hidden information to close that gap, but does not identify a single causal failure or show that every death is avoidable.

The 9×9/512-turn version is very different: 25.88% clears and 65.04% timeouts versus 88.57% privileged clears. Exploration costs matter under that smaller view and shorter deadline. This comparison changes both view size and deadline; it does not isolate their individual effects.

The slight no-rest clear advantage over privileged seek/destroy (90.04% versus 88.67%) is descriptive, not a superiority or significance claim. Different routes create different encounters and consume combat RNG differently; greedily pursuing the nearest hidden enemy is not an optimal policy. With rest, the privileged heuristic leads 93.55% versus 92.68%.

## Checks and limitations

Synthetic tests passed for both 9×9 and 15×15 formats: weakest adjacent target, known-terrain detour, refusal of an unknown shortcut, changed route after revealing that shortcut, frontier fallback, unknown-neighbor probing, persistence of observed terrain, forgetting hidden enemy records, rest masking and frozen inactive worlds. Every action in all six evaluation arms passed the original environment’s legal mask; all episodes terminated under the original deadline. Original simulator libraries were reused and hash-verified.

This v1 deliberately has no stale-enemy tracking or patrol fallback after all frontiers are exhausted. It waits when neither a visible target nor frontier route exists; rare timeouts remain (0.68% no rest, 0.78% with rest at 15×15). The aggregate idle count does not establish that this fallback explains all timeouts. No new training was performed, and learned results represent one training seed on a repeatedly used validation panel.

Reproduction:

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/test_local.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/run.py --local
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/report_local.py
```

Raw results: `results/local-destroy-los*.json`. Policy source: `diagnostics/seek-destroy-los/local_policy.cu`. Hash-named compiled libraries stay under ignored `learning-runs/seek-destroy-los-assets/`.

Policy source SHA256: `c361d4b551c68827eef962353656525cd85de9059bf341c03996f2566dccf23f`
