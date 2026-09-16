# Train and validate the no-travel policy with 2048 game turns

2026-09-15. Fresh seed 0, 10M training decisions, no travel action, 24 ordinary
enemies, zero ogres, 15x15 wall-blocked vision and LOS-gated waking. Same maps,
rewards and PPO hyperparameters as the early-checkpoint 512-turn training run.
Change the training episode deadline to 2,048 physical game turns and normalize
the observed elapsed-time input by 2,048 in both training and validation.

Keep model-only checkpoints at 0, 0.1M, 0.3M, 1M, 2M, 3M, 5M, 7.5M and 10M,
rounded up to PPO update boundaries, plus the bounded latest/best checkpoint
scheme. Train from initialization, without warm-starting the earlier policy.
At each milestone evaluate sampled and greedy behavior on 32 validation maps
x 32 episodes under the 2,048-turn deadline. No test maps are used.

Compare against `results/vision15-no-travel-early-2048.json`: that policy trained
with 512 turns but was evaluated with 2,048 turns and the same normalized clock.
The comparison therefore changes the training horizon and clock scaling, while
holding the evaluation horizon/clock fixed. Both see the same number of physical
training steps at each checkpoint; longer episodes change reset frequency and
the distribution of states encountered. This is a single-seed screen.

Implementation: `branches/vision15-train2048-v1`. Native training changes only
the time-input normalization; the native transition already accepts the physical
deadline as a runtime parameter. Runner, library key and wrapper consistently
use 2,048. Added native tests explicitly verify nontermination at tick 512 and
2047, timeout at 2048, and zero time after reset.

Smoke passed. Further validation covered 17,600 CPU/CUDA transitions and matched
the original simulator given the same actions and runtime deadline, except for
the intended clock normalization. Reward accounting, action masks and inactive
world freezing passed. Artifact: `results/vision15-train2048-validation.txt`.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-train2048-v1/scripts/run_curve.py \
  --suite gpu-d1/learning-runs/vision15-no-travel-train2048-10m \
  --results gpu-d1/results/vision15-no-travel-train2048-10m.json
```

The orchestrator checks that the old and new training jobs differ only in
`turn_limit`, verifies identical corpus hashes, and writes a checkpoint-by-
checkpoint comparison after training. Existing ignore rules keep weights,
compiled libraries and runtime logs local. Disk cap: 2 GiB; reserve: 5 GiB.
