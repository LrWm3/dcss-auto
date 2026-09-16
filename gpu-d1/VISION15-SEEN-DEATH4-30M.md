# Seen-floor / -4 death continuation to 30M

2026-09-16. Continue seed 0 of the seen-floor-count policy from 10,027,008 to
30,015,488 total decisions. Rewards remain +1 kill, +3 clear, -4 death,
+0.002 first-seen floor tile and -0.001 per turn. Keep 24 ordinary enemies,
no ogres or travel, 2048 physical turns, 15x15 wall-blocked vision and
LOS-gated waking. The extra observation remains seen-floor count / 1024.

Resume the full checkpoint, preserving model, optimizer, live worlds,
observations, masks, CPU/CUDA RNG, counters, training time and history.
Only the target step count changes. The launcher verifies the saved state
exactly after copying, checks corpus/source hashes, reuses the identical
native library and leaves the original checkpoint untouched. Runner changes
only add evaluation milestones at 15M, 20M and 25M.

Evaluate sampled and greedy policies at 15M, 20M, 25M and 30M on the same
32 validation maps x 32 episodes. The 256 training layouts and 100 untouched
test layouts stay unchanged. This is one continued training seed, not a
multi-seed comparison. Retain compact milestones plus latest/best under the
2 GiB suite cap and 5 GiB free-space reserve; existing ignores cover binaries,
weights and logs.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-seen-death4-30m-v1/scripts/run_continue.py
```

Source experiment: [10M results](VISION15-SEEN-DEATH4.md).
Output: `results/vision15-seen-death4-30m.json`. Training seconds are cumulative
from the original run; additional training time is also recorded separately.
