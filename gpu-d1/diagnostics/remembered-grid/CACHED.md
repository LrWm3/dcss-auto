# Cached remembered-map experiment

This separates an expensive, player-independent terrain encoder from a small per-decision policy. It is a new learned representation, not a numerically equivalent optimization of the original spatial policy.

The environment retains its exact remembered grid. A U-net receives three channels: known floor, known wall, and remembered stairs. Unknown terrain has neither floor nor wall marked. Its output is a 16-channel spatial feature map. The actor queries the 3x3 patch at its current position and combines this with a fresh 15x15 local observation, health, elapsed time, and cache age. All 19 original actions and their masks remain available. No route distances, frontier arrows, or search outputs enter the policy.

The global encoder does not receive player coordinates, current visibility, visited history, or enemy records. These dynamic fields remain local policy inputs where applicable; the experiment therefore changes global information as well as computation. It does not establish remembered enemy handling. There is no recurrent policy state.

## Cache rules

Refresh at reset. Thereafter refresh changed terrain when the configured interval expires, any stair tile changes, or at least 16 terrain cells differ from the snapshot. Reuse unchanged terrain indefinitely, even if the player moves. Enemy and local sensor inputs remain current. Reset the cache at every episode batch reset.

Intervals 1, 4 and 8 are evaluated. Training initially uses fresh terrain only; stale-map evaluation is consequently a robustness test, not an identically distributed supervised comparison. The unused age-input weight is set to zero before evaluation, removing an arbitrary initialized contribution without changing any fresh-map prediction. Select the longest interval whose mean validation success is within one percentage point of the best interval, before held-out evaluation.

## Training and PPO

The initial supervised/DAgger budget matches the earlier representation screen: seed 0, 12,000 updates, 256 examples per update, expert and learner-state buffers, and D4 augmentation. Select the checkpoint using validation success. The integer crop implementation replaces nearest grid sampling without changing values; edge equivalence is checked.

Then freeze the encoder and run a short, real PPO test. Store the queried feature patch rather than the whole map in PPO replay. Quantize that patch identically for rollout and update to preserve the old-policy probability comparison. Optimize only the local actor and critic: learning rate 3e-5, four epochs, clip 0.2, discount 0.999 per decision, GAE 0.95, value coefficient 0.25, entropy coefficient 0.001, gradient norm 0.5. Rewards are exit +1, death -1, otherwise zero. The deadline remains 256 physical turns including fixture history. There is no imitation anchor during PPO.

This first implementation uses synchronous batches of episodes. Finished worlds wait for the next batch. Only active decisions count toward throughput and the training budget; padded slots are separately reported. Evaluation time is excluded from training time. The source encoder is checked bit-for-bit unchanged after PPO.

The 80x70 benchmark measures synthetic network costs with AMP: one map encoding amortized over 1, 4, or 8 decisions, fresh local/query extraction, actor inference and four actor-training passes. This excludes simulator, change detection, buffer and GAE overhead. Actual refresh frequency depends on discoveries, so interval-based rates are scenarios rather than measured refresh rates. Navigation quality is still tested on the existing 32x32 synthetic maps, not full-size Crawl maps. The finite-depth convolutional encoder also has a finite receptive field; arbitrary-distance route planning is not guaranteed.

## Commands

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_cached.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/run.py --arm terrain --architecture cached --updates 12000
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/cached_experiment.py quality
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/cached_experiment.py benchmark
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/cached_experiment.py ppo --decisions 250000
```

Run those sequentially on an otherwise idle GPU. Artifacts are bounded to best/latest supervised checkpoints and one PPO checkpoint under ignored `learning-runs/remembered-grid/terrain-cached`. Checked JSON summaries are written under `results`.
