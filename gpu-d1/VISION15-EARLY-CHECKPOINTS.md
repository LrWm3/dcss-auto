# Early no-travel learning under the original training deadline

2026-09-15. The original storage policy retained latest/best weights; both are
from 30M for the no-travel run, so its 10M weights were no longer available.
Replay seed 0 with the original 15x15 no-travel PPO task to 10M decisions,
retaining compact model-only weights at additional milestones.

Training remains unchanged: 24 ordinary enemies, zero ogres, 512 physical game
turns, nine movement/attack/wait actions, wall-blocked vision, LOS-gated waking,
same rewards and PPO hyperparameters, 256 training maps. Native simulator and
environment source are byte-identical to the original branch. Changes in the
isolated `branches/vision15-learning-curve-v1` runner only add evaluation milestones
and retained compact weights. Validation forks/restores the training RNG.

Requested milestones: 0, 0.1M, 0.3M, 1M, 2M, 3M, 5M, 7.5M, and 10M decisions.
Actual counts round up to complete PPO updates (32,768 decisions). Each snapshot
contains model weights and metadata, not optimizer or live environment state.
The existing latest checkpoint remains resumable, and the whole suite retains
the 2 GiB cap/5 GiB free-space reserve. Nine compact snapshots total about 5 MB;
existing ignore rules keep all checkpoint files out of Git.

After training, evaluate every checkpoint without travel at a 2,048-game-turn
cutoff, with no further weight updates. Use the same 32 validation maps x 32
episodes and sampled seed 900000. Report the original 512-turn validation and
two longer-deadline evaluations: elapsed turns / 2048 as the budget clock, plus
elapsed turns / 512 to preserve the original clock units. The latter can exceed
the training input range. No test maps are used. Check shared milestones against
the original 30M run's sampled/greedy outcomes and report whether they reproduce;
do not assume numerical identity merely because the seed is the same.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-learning-curve-v1/scripts/run_curve.py \
  --suite gpu-d1/learning-runs/vision15-no-travel-early-10m \
  --results gpu-d1/results/vision15-no-travel-early-2048.json
```

The orchestrator trains before evaluating and stops if either stage fails.
Re-running the command resumes training through the original storage machinery;
evaluations are read-only with respect to saved weights and verify hashes before
and after. Progress log: `results/vision15-no-travel-early-2048.log`.

Smoke validation retained both 0 and 512-decision compact checkpoints, verified
the nine-action head and absence of optimizer/live worlds in those files, and
checked the original native/environment sources and Python syntax. Artifact:
`results/vision15-learning-curve-validation.txt`.
