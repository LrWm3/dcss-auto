# 15x15 no-travel continuation matched to travel training time

2026-09-15. Continue seed 0 of `vision15-frontier-30m` without changing
observations, rewards, PPO hyperparameters, maps, or the 512-turn deadline.
Restore the latest 30,015,488-decision checkpoint, including optimizer, live
worlds, random states, and cumulative training time. Preserve the original suite.

The no-travel arm previously trained for 192.1328 seconds; the travel arm trained
for 274.7969 seconds. Add 82.6641 measured training seconds, stopping at the first
complete PPO update reaching the target. Timing includes rollout and optimization,
with CUDA synchronization, but excludes startup, validation, and checkpoint I/O.
The 100M decision ceiling is a safety cap, not the intended stopping criterion.

The isolated `branches/vision15-time-match-v1` runner changes only the training
time stopping condition and guarantees evaluation at that stopping point.
The continuation helper verifies unchanged environment/model dependencies and
corpus hashes, reuses the original compiled simulator, records checkpoint and
source provenance, and uses the existing bounded checkpoint storage.

Final validation uses the same 32 validation layouts, 32 episodes per layout,
and sampled/greedy evaluation procedure. Compare final checkpoints, rather than
selecting the best observed result. This is a single-seed comparison at matched
measured training time on this machine, not matched physical turns or decisions.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-time-match-v1/scripts/continue_time_match.py \
  --source gpu-d1/learning-runs/vision15-frontier-30m \
  --output gpu-d1/learning-runs/vision15-no-travel-time-match
```

The same command resumes an interrupted continuation. Runtime artifacts remain
ignored; compact results are recorded separately after validation.

## Completed result

| Final sampled validation | No travel, original | No travel, continued | Travel |
|---|---:|---:|---:|
| Policy decisions | 30,015,488 | 42,663,936 | 30,015,488 |
| Training seconds | 192.133 | 274.985 | 274.797 |
| Clear rate | 20.02% | 19.73% | 19.73% |
| Death rate | 22.27% | 17.87% | 15.43% |
| Timeout rate | 57.71% | 62.40% | 64.84% |
| Mean kills | 18.35 | 18.94 | 19.32 |
| Floor coverage | 78.95% | 81.00% | 81.73% |
| Shaped return | 19.83 | 20.48 | 20.89 |

The continuation added 12,648,448 decisions and 82.852 training seconds,
overshooting the target by 0.188 seconds at an update boundary. Final evaluation
matches the saved final decision count. The two time-matched policies each clear
202 of 1,024 validation episodes. Additional no-travel training improved survival
and partial progress, but did not improve clearing at this checkpoint. This
single seed does not establish convergence or equivalence of the approaches.

Artifact: `results/vision15-time-match.json` includes both evaluation modes and
per-map metrics for all three checkpoints. Native source and observation/model
dependencies were hash-checked against the original suite; Python syntax and
final timing/validation-count assertions passed. No simulator changes were made.
