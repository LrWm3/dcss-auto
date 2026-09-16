# Wait for awake enemies before engaging

Same 1,024 validation episodes, 24 enemies, 15×15 wall-blocked LOS, LOS-gated waking, 2,048 policy decisions and rest as the hallway-retreat comparison. No training or simulator change.

The new optional `wait_for_awake` rule replaces ordinary pursuit with wait when any currently visible enemy is awake and no visible enemy is adjacent. Adjacent combat retains the existing target selection. Sleeping-only sightings retain ordinary pursuit; no visible enemies permits rest/exploration. Hallway retreat retains priority, including its original strict destination and first-step direction requirements. A retreat lockout does not prevent approach waiting. The rule checks current visibility each decision; it does not remember an enemy that leaves sight.

| Pursuit | Retreat | Previous clears | New clears | Previous deaths | New deaths | New timeouts | New mean physical turns |
|---|---|---:|---:|---:|---:|---:|---:|
| privileged | False | 958 | 995 | 66 | 29 | 0 | 468.4 |
| privileged | True | 993 | 1000 | 31 | 24 | 0 | 479.3 |
| local | False | 949 | 983 | 67 | 30 | 11 | 675.6 |
| local | True | 986 | 993 | 29 | 23 | 8 | 682.6 |

The previous regression episode 863 now clears with 24 kills in 462 physical turns.

Waiting alone closes much of the gap to the earlier retreat policy on this panel. Adding waiting to retreat improves clears by seven episodes in each pursuit variant. These are descriptive comparisons on one repeatedly used validation panel, not a significance claim. Changed action sequences also change subsequent combat RNG consumption.

The privileged retreat variant now averages 53.1 approach waits and 9.8 retreat steps per episode (previously 22.6 retreat steps). The results are consistent with waiting reducing the need to reposition, but do not isolate whether regeneration, enemy arrival timing, or avoiding advancing into more enemies explains the benefit.

Checks: rotated awake sightings wait; adjacent enemies trigger combat; sleeping-only sightings do not trigger waiting; rest remains available without visible enemies; retreat movement overrides waiting; lockout permits waiting; inactive worlds remain inactive. Existing retreat tests pass. All evaluated actions satisfy the simulator mask. Original library hash verified.

Reproduce:
```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/test_wait_awake.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/test_retreat.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/run_retreat.py --wait-for-awake
```

Raw results: `results/los-hallway-wait-awake.json`. Previous policies/results remain available unchanged when the new option is omitted.
