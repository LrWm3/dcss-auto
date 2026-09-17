# Cached remembered-map experiment

## Initial results

The first seed demonstrates useful global navigation and much cheaper frozen-encoder updates, but it loses known-stair navigation quality. This is an experimental tradeoff, not a replacement for the stronger spatial policy yet.

| Policy | Known stairs, greedy | Exploration, greedy | Longer known stairs | Longer exploration |
|---|---:|---:|---:|---:|
| Original spatial policy | 92.19% | 90.23% | 53.91% | 67.19% |
| Cached encoder, interval 1 | 69.14% | 91.41% | 32.03% | 63.28% |
| Cached encoder, interval 4 | 69.14% | 87.50% | 30.47% | 61.72% |
| Cached encoder, interval 8 | 69.92% | 86.33% | 31.25% | 58.59% |

Validation selected interval 4 under the prespecified tolerance rule. Its sampled held-out exits were 82.42% for known stairs and 94.53% for exploration. The paired distant-goal diagnostic passed 24/24 pairs; erasing the global readout reduced this to 0/24 pairs (50% individual first actions). Thus the global representation carries useful remote goal information, despite its weaker broader route selection.

All three intervals passed the ordinary threat-backtracking fixtures. On the longer fixtures, interval 1 passed 32/32, interval 4 passed 28/32, and interval 8 passed 29/32; the failures were deaths. This is a concrete limitation of stale terrain features in this first implementation.

Supervised training took 346.7 seconds excluding validation: 960,439 collected decisions and 3,072,000 sampled supervised examples. The selected checkpoint was update 12,000. This is one seed on existing synthetic regression splits.

| Full 80x70 network computation | Four-pass PPO decisions/s estimate |
|---|---:|
| Previous optimized spatial policy, trained end to end | 4,370 |
| Frozen encoder, one refresh per 1 decisions | 13,471 |
| Frozen encoder, one refresh per 4 decisions | 30,892 |
| Frozen encoder, one refresh per 8 decisions | 39,380 |

These costs change the optimization problem: the cached model freezes its global encoder, while the previous baseline trains it. They are not equal-learning-capacity speed comparisons. Caching every four decisions reduces the estimated network cost about sevenfold. No compiler is needed for this cached benchmark. A replay observation is approximately 2,851 bytes rather than 61,600 bytes for the full 11-channel grid, about 22 times smaller; this excludes common PPO fields. The persistent full-map feature cache adds 179,200 bytes per environment at FP16.

The refresh fractions in raw evaluation JSON count all observation slots, including inactive and padded worlds. Do not interpret those fractions as refreshes per active game decision. Bucketing also encodes some duplicate slots; both counts are recorded.


AMP validation of the selected supervised checkpoint preserved all 24 paired-goal successes. Held-out known-stair exits were unchanged at 69.14%; exploration was 87.89% versus 87.50% in FP32. See [AMP regression](../../results/remembered-grid-cached-amp-quality.json).

## Frozen-encoder PPO result

The 252,133-active-decision run took 55.49 seconds excluding validation/test evaluation (4,544 active decisions/s). This is FP32 on 32x32 maps, batch 128, with only 19.36% active slots because completed episodes wait at a batch barrier. It is a functional end-to-end proof, not the optimized throughput of the AMP full-size network benchmark. Replacing synchronous waves with individual episode resets is required before making a fair high-throughput pipeline comparison.

| Interval 4 held-out result | Before PPO | After PPO |
|---|---:|---:|
| Known stairs, greedy | 69.14% | 74.22% |
| Exploration, greedy | 87.50% | 87.50% |
| Known stairs, sampled | 82.42% | 82.81% |
| Exploration, sampled | 94.53% | 91.41% |

The encoder remained bit-for-bit unchanged. This shows that PPO updates can run using cached features and can change navigation behavior; it does not demonstrate a reliable overall learning gain. Known-stair validation actually fell from 73.44% to 71.09%, while exploration validation rose from 87.50% to 91.41%. Sampled evaluations use different random draws and are descriptive rather than a paired significance test. One seed and one short PPO run cannot establish an improvement.

The useful next question is whether more joint pretraining and training with the actual refresh schedule can close the quality gap before freezing. The current design retains distant-goal information but does not preserve the original policy's route competence. It should not replace that policy yet.

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
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/cached_experiment.py amp_quality
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/cached_experiment.py ppo --decisions 250000
```

Run those sequentially on an otherwise idle GPU. Artifacts are bounded to best/latest supervised checkpoints and one PPO checkpoint under ignored `learning-runs/remembered-grid/terrain-cached`. Checked JSON summaries are written under `results`.

[Quality details](../../results/remembered-grid-cached-quality.json), [compute benchmark](../../results/remembered-grid-cached-performance.json), [PPO run](../../results/remembered-grid-cached-ppo.json).
