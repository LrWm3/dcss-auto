# Model plus waiting only

Frozen 10M rest/sleep seed-0 model, same 1,024 validation episodes, 24 enemies, 15×15 wall-blocked LOS and 2,048 policy decisions. No retraining.

Override the model action with wait if at least one currently visible enemy is awake and **no visible enemy is adjacent**. Otherwise use the model action unchanged, including attacks, target selection, movement and rest. An adjacent sleeper also prevents overriding the model. There is no retreat, heuristic attack choice, pursuit or encounter latch. Sampled model actions are drawn every decision before the override, matching baseline evaluation RNG consumption.

## Results

| Policy | Clears | Deaths | Timeouts | Mean physical turns | Mean forced-wait decisions |
|---|---:|---:|---:|---:|---:|
| learned-sampled | 867 (84.67%) | 148 | 9 | 625.3 | 0.0 |
| learned-greedy | 609 (59.47%) | 288 | 127 | 898.8 | 0.0 |
| waiting-sampled | 894 (87.30%) | 118 | 12 | 672.9 | 42.4 |
| waiting-greedy | 629 (61.43%) | 268 | 127 | 916.9 | 38.7 |

For context, previous full encounter-heuristic hybrids:

| Policy | Clears | Deaths | Timeouts |
|---|---:|---:|---:|
| awake-sampled | 991 | 18 | 15 |
| visible-sampled | 1001 | 22 | 1 |
| awake-greedy | 887 | 17 | 120 |
| visible-greedy | 898 | 21 | 105 |

## Paired outcomes against model alone

| Model mode | Newly clear | Previously clear, now fails |
|---|---:|---:|
| sampled | 98 | 71 |
| greedy | 162 | 142 |

Both learned-only controls reproduce their saved clear/death/timeout rates, kills and physical turns exactly. All evaluated actions passed the legal mask and every episode terminated. Waiting-gate checks cover distant awake enemies, adjacent enemies, sleeping-only sightings, no enemies, inactive worlds and an adjacent sleeper with a distant awake enemy. The reported forced-wait count includes decisions where the model might already have selected wait.

These are descriptive results on a reused validation panel for one frozen model. Changes to movement, regeneration, encounter timing and combat randomness are not separately isolated. No general statistical significance or transfer claim is made.

Reproduce:

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/run_hybrid.py --waiting-only
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/report_waiting_only.py
```

Raw: `results/los-model-waiting-only.json`.
