# Privileged seek-and-destroy versus learned LOS policies

2026-09-16. Each heuristic was evaluated inside the original LOS branch using its original verified evaluation library, the same 32 validation maps × 32 initial placements, seed 900000, and 24 ordinary enemies. Corpus hashes and player/enemy configuration arrays match across all five cases. Learned results below are the saved final sampled-policy validations, not newly trained policies.

| Learned configuration | Training decisions | Evaluation budget | Learned clear % | Privileged seek/destroy clear % |
|---|---:|---|---:|---:|
| 9×9 LOS, original screen | 30.02M | 512 turns | 16.41 | 88.57 |
| 15×15 LOS, baseline | 10.03M | 2048 turns | 61.52 | 88.67 |
| 15×15 LOS, seen count / death −4 | 30.02M | 2048 turns | 78.71 | 88.67 |
| 15×15 LOS, sleep status / wait | 10.03M | 2048 decisions | 80.37 | 88.67 |
| 15×15 LOS, sleep status / rest | 10.03M | 2048 decisions | 84.67 | 93.55 |

For the rest-enabled row, the heuristic rests whenever the original LOS rest mask permits it; all other rows use the plain heuristic. Rest is blocked by **any visible enemy**, including sleeping enemies, in these LOS branches. This differs from the new full-map rule (no awake enemy within seven tiles). The decision-budget rest row may consume more than 2048 physical turns, though neither heuristic reaches its deadline.

The heuristic reads the complete map, all live enemy locations and HP from native state, including hidden enemies. It attacks the lowest-HP adjacent enemy; otherwise it takes a shortest-path step toward the nearest living enemy. It keeps that privileged knowledge even while the environment uses LOS-gated waking. The learned policies only receive visible enemies plus their configured local/remembered terrain, ring, and known-map frontier/route cues. Thus this is a privileged reference baseline, not an equal-information comparison or an optimality bound.

## Outcomes and efficiency

| Configuration | Learned death % | Learned timeout % | Heuristic death % | Heuristic timeout % | Learned mean physical turns | Heuristic mean physical turns |
|---|---:|---:|---:|---:|---:|---:|
| 9×9 LOS, original screen | 21.19 | 62.40 | 11.33 | 0.10 | 429.3 | 325.1 |
| 15×15 LOS, baseline | 37.40 | 1.07 | 11.33 | 0.00 | 473.4 | 325.1 |
| 15×15 LOS, seen count / death −4 | 20.41 | 0.88 | 11.33 | 0.00 | 543.0 | 325.1 |
| 15×15 LOS, sleep status / wait | 18.46 | 1.17 | 11.33 | 0.00 | 522.5 | 325.1 |
| 15×15 LOS, sleep status / rest | 14.45 | 0.88 | 6.45 | 0.00 | 625.3 | 426.2 |

Mean physical turns includes all outcomes, not only clears. Clear-only heuristic timings are retained in raw JSON. The rest-enabled environment also has a plain-heuristic control: 88.67% clears without using rest, versus 93.55% when resting whenever eligible.

## Interpretation

The recent sleep-status LOS models are 8.30 percentage points below the matching plain heuristic (80.37% versus 88.67%), and 8.89 points below the heuristic with rest (84.67% versus 93.55%). Timeouts are approximately 1%; most of the remaining gap appears as deaths. This does not imply that all those deaths are avoidable, nor that privileged knowledge is the sole cause of the gap. Better encounter choice, pathfinding, target selection and healing can all contribute.

The earlier 9×9/512-turn policy has a much larger gap and 62.40% timeouts. Privileged seek/destroy has only one timeout in 1,024 episodes under the same deadline. Its higher completion rate shows that this deadline is sufficient for direct pursuit in nearly all these placements; it does not remove the exploration burden faced by a partially informed policy.

The full-map experiment previously gave 86.04% clears for plain seek/destroy and 91.89% with rest. Those values should not be copied unchanged into the LOS comparisons: wall-gated waking changes encounters. In the matched LOS simulations, plain seek/destroy gives identical results across the 2048-budget variants (88.67%); the 512-turn case loses one clear to timeout (88.57%). Reward and observation differences do not affect this fixed heuristic’s actions or its combat rules.

The recent learned LOS models are much closer to their privileged reference than the new 10M full-map model (14.26% versus 86.04%). This is not a clean test of LOS versus full visibility: the full-map run changes architecture, removes frontier guidance and exploration reward, changes waking/rest rules, and has a different training distribution. It does establish that more raw information alone has not translated into stronger learned play in that configuration.

All learned comparisons involve one training seed per configuration and a repeatedly used validation panel. No untouched test evaluation or multi-seed significance claim is made. Policies share starting environments, but their actions cause subsequent RNG streams to diverge.

## Reproduction

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/run.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/report.py
```

The evaluator performs no training, imports each original branch in an isolated process, verifies library hashes, checks every heuristic action is legal, freezes finished episodes, and requires all 1,024 episodes to terminate. Raw outputs are `results/seek-destroy-los*.json`, with saved learned metrics, map/library hashes, configuration and new heuristic results.
