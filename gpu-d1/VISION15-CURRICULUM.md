# Short-to-long episode curriculum

2026-09-15. Seed 0, no travel, 24 normal enemies, no ogres, 15x15 wall-blocked
vision, LOS-gated waking. Same rewards, PPO settings and 256 training layouts as
both fixed-deadline baselines. Train at 512 physical turns through 2,031,616
policy decisions, then switch to 2,048 turns through 10,027,008 decisions.
Validate on the same 32 held-out validation layouts x 32 episodes, with a
2,048-turn deadline and elapsed turns / 2048 as the time input throughout the
comparison. The separate test set is untouched.

Hypothesis: shorter early episodes provide more useful experience by resetting
unproductive episodes sooner. This screen tests the schedule's performance;
it does not directly measure that mechanism or separate the effect of clock
normalization from deadline changes.

## Implementation and checks

The original retained 2M snapshot contains model weights only. Replay the
original 512-turn training to recover optimizer, live environments and RNG.
Assert that every model tensor exactly matches the original 2M snapshot.
Transfer weights, optimizer, live worlds, masks, RNG and cumulative counters
without resetting episodes. Divide the saved elapsed-time observation by four
and continue using the already-tested 2048-turn simulator. Clear old validation
history and best-model selection because those evaluations used 512 turns.
Immediately revalidate at the switch before taking another training step.

Passed: exact replay weight equality, identical map hashes, matching baseline
job configuration except the intended schedule, native/wrapper source equality
to the fixed-2048 experiment, compiled-library hash, exact switch-point outcome
and turn metrics against the earlier extended evaluation, Python syntax,
recorded source hashes and outcome accounting. Native behavior is unchanged
from the fixed-2048 branch's tested implementation.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-curriculum-v1/scripts/run_curriculum.py \
  --stage1 gpu-d1/learning-runs/vision15-curriculum-stage1-2m \
  --stage2 gpu-d1/learning-runs/vision15-curriculum-stage2-10m \
  --results gpu-d1/results/vision15-curriculum-10m.json
```

This orchestrator depends on retained baseline artifacts and the fixed-2048
compiled library. Each stage has a 2 GiB disk cap and requires 5 GiB free space.
Existing ignore rules exclude weights, build products, runtime logs and launch
metadata. Compact results and experiment source are tracked.

## Results

Sampled policy, all evaluated at 2048 turns. Mean turns includes every outcome,
including early deaths, so lower values alone do not demonstrate efficiency.

| Decisions | Fixed 512 clear | Curriculum clear | Fixed 2048 clear | Curriculum mean turns | Cumulative training seconds |
|---|---:|---:|---:|---:|---:|
| 2,031,616 | 49.22% | 49.22% | 40.72% | 556.0 | 10.08 |
| 3,014,656 | 51.86% | 52.93% | 46.09% | 488.8 | 17.05 |
| 5,013,504 | 60.06% | 52.15% | 54.88% | 458.8 | 31.75 |
| 7,503,872 | 63.38% | 59.28% | 58.20% | 489.7 | 50.84 |
| 10,027,008 | 65.43% | 65.43% | 61.52% | 509.1 | 70.58 |

At 10M:

| Training schedule | Clear | Death | Timeout | Mean turns |
|---|---:|---:|---:|---:|
| Fixed 512 | 65.43% | 32.62% | 1.95% | 518.5 |
| 512 then 2048 | 65.43% | 32.52% | 2.05% | 509.1 |
| Fixed 2048 | 61.52% | 37.40% | 1.07% | 473.4 |

Curriculum training took 70.576 seconds, including 10.078 seconds before the
switch; this excludes compilation, evaluation and checkpoint I/O. Fixed-512
training took 60.557 seconds and fixed-2048 took 69.549 seconds in their runs.

The curriculum matches the fixed-512 final clear count (670/1024), but falls
behind it at 5M and 7.5M. There is no demonstrated benefit to switching at 2M.
The final advantage over fixed-2048 is consistent with an early-training effect,
but one seed and a changed clock scale cannot establish that explanation.
Failures at the end are predominantly deaths, not timeouts.

Artifact: `results/vision15-curriculum-10m.json`, including both baseline metrics,
sampled/greedy evaluations, per-map outcomes, timing and checkpoint provenance.
