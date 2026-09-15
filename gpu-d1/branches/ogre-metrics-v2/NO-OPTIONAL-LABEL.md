# Explicit required/optional label ablation

Fresh seed-0 training to 50M total decisions, queued after `ogre2-baseline-150m-fast` completes successfully. Two optional ogres plus 24 required ordinary enemies; 256 training layouts, 32 validation layouts × 32 episodes, 1024-turn budget. Fast implementation and the existing wake, proximity, kill, death and clear diagnostics are retained.

The only input change is setting all 40 explicit kill-required entries (`421 + 8*i` in the fixed 741-wide observation) to zero, during both training and evaluation. Observation width, initialization, slot order, type IDs, HP, relative positions, masks, rewards and game dynamics are unchanged. This removes the explicit label, not the ability to infer optional status from fixed slots or monster type.

The wrapper entry point applies masking to reset/step observations in worker subprocesses as well as the coordinator. Its source is included in the suite manifest. Native simulator code and the running baseline's source manifest are untouched. CPU comparison over 1,600 world turns verified identical native states, transition outputs, masks and all non-label observation entries.

Primary comparison: sampled clear rate at the same 50,003,968-decision checkpoint versus the existing labelled baseline (30.6640625%). Secondary: ogre-inflicted deaths, wake fraction, awake-ogre adjacency/proximity, and successful clears retaining both ogres. This is one seed, so differences are screening evidence rather than a stable effect-size estimate. This is training from scratch, not an evaluation-only mask on the trained labelled policy.

Queued command (from repository root):

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/ogre-metrics-v2/scripts/run_no_optional_label.py --after-suite gpu-d1/learning-runs/ogre2-baseline-150m-fast --steps 50000000 --seeds 0 --output gpu-d1/learning-runs/ogre2-no-optional-label-50m
```

Repeat the same command to resume if interrupted, including `--after-suite` so the source manifest remains identical. The queue refuses to start if the preceding suite stops unfinished. Log: `gpu-d1/results/ogre2-no-optional-label-50m-console.log`. One latest and one best checkpoint are retained within the runner's 2 GiB suite budget.
