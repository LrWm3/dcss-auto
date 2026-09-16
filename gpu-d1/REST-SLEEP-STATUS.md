# Visible sleep status with rest-to-full

Rerun the two fresh seed-0 10M-decision arms from REST-TO-FULL.md, adding enemy sleep information. The earlier checkpoints and diagnostic results remain the no-status comparison.

The observation grows from 959 to 999 floats. The appended 40 values correspond to the existing 40 encounter-ordered enemy records: +1 for a visible sleeping enemy, -1 for a visible awake enemy, and 0 for a hidden/dead/empty slot. Status is exposed only inside current wall-blocked LOS; remembered enemies outside LOS do not retain status. D4 transforms preserve these scalar values and their association with enemy records. No energy phase is exposed.

All original initial weights are preserved; the 40 new input columns start at zero. Both fresh policies share identical initialization. Rewards, layouts, 24 enemies, one-third clumping, 15×15 LOS, LOS-required waking, PPO settings, 2048-decision deadline, and action masks are unchanged. A visible sleeper still prevents the rest macro: the model must learn primitive waiting or moving out of sight if it wants to heal first. Native sleep/wake behavior is unchanged.

## Checks and execution

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-rest-sleep-v1/scripts/assets.py
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-rest-sleep-v1/scripts/preflight.py
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-rest-sleep-v1/scripts/pipeline.py
```

Preflight checks visible sleeping/awake values, no hidden or remembered-hidden status leakage, D4 invariance, old initialization preservation, paired initialization, native rest equivalence and masks, decision deadlines, and PPO update/resume. The pipeline trains wait-only then rest-enabled to 10,027,008 decisions, performs ordinary held-out validation, then runs both sampled and greedy recovery evaluations automatically. It uses the same three positions, three player HP levels, two enemy strengths, eight orientations, and 128 combat seeds as the original probes. No diagnostic scenarios are mixed into training.

Status: `gpu-d1/learning-runs/vision15-rest-sleep/pipeline-status.json` and `status.json`. Logs: `pipeline.log`. Disk-bounded checkpoints use the existing 2 GiB suite cap and 10 GiB minimum free-space check.

Outputs: `gpu-d1/results/rest-sleep-training-summary.json`, four `rest-sleep-recovery-*.json` files, and `rest-sleep-comparison.md`. Training time is reported separately from evaluation. Expected duration is roughly 11–13 minutes based on the prior 10½-minute paired pipeline, subject to GPU load.

This is one trained seed per configuration. The larger diagnostic episode sample reduces rollout noise, not uncertainty across independently trained policies.

## Completed results

Both arms completed 10,027,008 decisions. Training took 213.3 seconds for wait-only and 224.3 seconds for rest-enabled; the complete training, validation, and diagnostic pipeline took 675.0 seconds (11m15s).

Sampled ordinary-floor clear rates without → with sleep status: wait-only 81.15% → 80.37%; rest-enabled 80.76% → 84.67%. Rest-enabled death rate fell from 18.36% to 14.45%; its timeout rate stayed at 0.88%. These are one-seed results.

The central visible-sleeper preparation failure remains: at low HP neither new model selected any primitive waits while the visible enemy remained asleep. At half HP, such waits were extremely rare (at most 0.2% of episodes in the visible cases). Wake HP remained near starting HP. Rest-enabled policies only occasionally moved out of view to rest.

Outside vision, the new rest-enabled policy recovered more consistently. At 2 HP, rest-before-wake rose from about 70% to 92% averaged across enemy profiles; at 9 HP, from 93% to 99%. Against the harder enemy outside vision at 2 HP, survival rose from 68.3% to 86.2%. The new model's initial rest probability rose from 41.2% to 81.6% at 2 HP. The enemy is hidden at that point, so its sleep status is zero: this reflects a changed learned policy, not knowledge of that hidden enemy. It does not establish that sleep status alone reliably produces the gain across training seeds.

Full per-condition comparisons, including greedy results, are in `results/rest-sleep-comparison.md`. The sleep input did not by itself solve waiting-to-heal around visible sleeping enemies within this 10M training budget.
