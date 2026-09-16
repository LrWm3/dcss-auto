# Movement during adjacent combat: frontier and enemy alignment

Replays the original sampled 10M seed-0 LOS/rest/sleep model on the same 1,024 validation episodes. No policy intervention. Clear/death counts and mean physical turns exactly reproduce the saved baseline.

There were **70,859 directional non-attacks while a visible enemy was adjacent** (the prior 70,989 non-attacks also included 130 waits). The frontier route existed in 70,373 of these states. Its next step was a legal non-attack move in 61,382 states; frontier-match percentages below use that eligible denominator.

| Measure | All adjacent movements | Multiple adjacent enemies | HP ≤6 |
|---|---:|---:|---:|
| Exact frontier next-step match, when movable | 76.9% | 64.9% | 64.4% |
| Uniform legal-movement exact-match reference | 40.1% | 36.8% | 35.0% |
| Positive directional alignment with frontier next step | 86.3% | 81.7% | 77.5% |
| Step points away from adjacent-enemy centroid | 73.6% | 77.4% | 62.3% |
| Reduces adjacent-enemy count if visible enemies stay still | 82.7% | 91.8% | 71.5% |

The uniform reference accounts for walls and occupied attack directions: it is not 1/8, since many states have few legal movement choices. This is a geometric reference, not an evaluated random-policy outcome.

47,182 moves exactly follow the frontier route, **66.6% of all adjacent movements**, including states where no movable frontier cue is available in the denominator.

When the highest-probability action is movement with probability at least 80%, 88.0% of sampled moves match the movable frontier cue; that greedy movement direction itself matches 90.3%. Across all sampled movement states where the greedy action is also movement, greedy direction matches 81.7% of movable cues.

There is no strong absolute compass preference in this panel: N/E/S/W counts are 10,267/10,416/10,204/10,238; diagonal counts range 7,180–7,718. Cardinal movement is more common than diagonal movement, but this alone cannot separate geometry from policy preference.

## Interpretation

The movement is strongly structured and aligned with the supplied frontier route. Describing it as arbitrary movement or merely sampling errors would miss this pattern.

However, frontier following and enemy separation overlap: 77.3% of exactly frontier-matching moves point away from the adjacent-enemy centroid, and 86.5% reduce the number of adjacent enemies under static-enemy geometry. Correlation therefore does not identify the policy's motive. It could be continuing exploration while enemies pursue, disengaging along the exploration route, or a mixture. This audit does not prove that the exploration reward caused the behavior.

The static-enemy calculations happen before monsters respond: they are **not** evidence that the player actually escapes or avoids damage after their turn. Whether these moves provide useful regeneration, expose new enemies or create repeated chase behavior requires trajectory or counterfactual analysis.

Together with the previous forced-attack improvement, this supports investigating whether frontier-directed movement sometimes competes with finishing fights. It does not establish that suppressing the frontier cue would help: removing an input from a frozen model can also put it outside its training distribution.

## Reproduction

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/audit_movement_alignment.py
```

Raw aggregates and provenance: `results/los-movement-alignment.json`. Summaries are decision-weighted and describe one frozen model on a reused validation panel. No training performed.
