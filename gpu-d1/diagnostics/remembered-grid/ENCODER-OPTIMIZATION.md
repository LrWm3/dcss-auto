# Symbolic encoder: redundant pooling and channels-last

This four-arm screen keeps the optimized GRU, all learned weights, observations,
15x15 local/tactical crops, 16x16 global map, and action space unchanged. It tests
(1) the existing encoder, (2) skipping redundant pooling, (3) channels-last CNN
weights/inputs, and (4) both changes. No retraining is required.

## Implementation

The three CNNs produce 4x4 activations and then call AdaptiveAvgPool2d(4). That
operation is mathematically identity. `SkipIdentityPool` returns the input for
this case, and uses ordinary adaptive pooling for other spatial sizes. Keeping
the module in the same Sequential slot preserves checkpoint parameter names.

`FastSymbolicPolicy` accepts `skip_identity_pool` and `channels_last` options.
`configure_encoder` applies them to an existing checkpoint before optimizer
creation. Channels-last converts CNN weight storage and prepared map tensors;
it does not permute logical channel order or the flattened features supplied to
the learned linear layers. `encode_prepared` accepts either layout, so externally
prepared inputs work too. Reference defaults remain unchanged.

The supervised runner exposes `--encoder-fast` (both options), requiring `--fast`
or minGRU. It records the option and source hashes, writes a separate `-encoder`
output directory, and creates the optimizer after layout changes. This flag does
not automatically enable mixed precision or change batch sizes; current runner
training is FP32, where the benchmark found no consistent improvement.

## Corrected full-network benchmark

This uses the fixed benchmark with separate autocast contexts for burn-in and
learning; every trainable parameter must receive finite gradients. No missing
encoder/core backward passes. GPU: Quadro RTX 5000 Max-Q, PyTorch 2.6.0.

80x70 input maps, 512-decision inference batch, 16 burn-in + 16 learning steps,
four PPO-shaped optimizer passes. Includes CNNs, GRU, heads, Adam, clipping,
scaling, and inference preprocessing. Excludes simulation/export, rollout
storage, GAE, and actual PPO learning. These are network-only throughput
estimates, not end-to-end PPO decisions/s.

Three timing rounds after warmup per arm; the experiment was repeated with arm
order reversed. Large configuration uses FP16 autocast, learning batch 4096,
and precomputed deterministic symbolic inputs (not cached learned features).

| Arm | Optimizer ms | Network decisions/s |
|---|---:|---:|
| Reference | 31.82–32.02 | 26,329–26,617 |
| Skip identity pooling | 25.72–25.83 | 31,942–32,003 |
| Channels-last | 16.75–17.19 | 42,536–44,577 |
| Both | 16.65–16.92 | 42,460–45,756 |

The combined configuration is about 1.6–1.7x the reference in matched runs, with
nearly 1.9x faster optimizer steps. Layout accounts for the largest benefit.
Pooling/layout benefits overlap: pooling implementation cost itself depends on
memory layout, so the two gains are not additive. Inference timing varied more
than optimizer timing; ranges preserve both runs rather than selecting a best
number. The pooling-only improvement is about 20% in network throughput.

At small FP32 learning batch 256, reference was 7,301–7,473 network decisions/s;
combined was 5,973–7,449. Timing was variable and there is no consistent gain.
The stronger mixed-precision large-batch result is not a claim of faster small
FP32 training. The flags are opt-in for this reason.

## Reproduction

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_symbolic_encoder.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/benchmark_symbolic_encoder.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/benchmark_symbolic_encoder.py --reverse
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/symbolic_encoder_quality.py
```

To opt into both encoder changes in a future supervised run:

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/symbolic_run.py --kind gru --fast --encoder-fast --updates 12000
```

Models/checkpoints/generated maps remain under ignored `learning-runs`; source,
compact benchmark/quality artifacts and profiles are tracked. Artifacts:
`results/symbolic-encoder-benchmark{,-reverse}.json`,
`results/symbolic-encoder-quality.json`, and
`results/symbolic-encoder-profile-{reference,both}.txt`.

## Correctness and held-out behavior

Checks passed for exact identity-pool values/gradients, pooling fallback on other
sizes/targets, unchanged checkpoint keys and parameter counts, encoder features
and learned gradients in FP32/AMP on 32x32 and 80x70 map inputs (including map
boundaries), and the actual padded sequence training loss with all encoder/core
gradients compared. The policy still has 229,476 learned parameters.

The existing 12k GRU checkpoint was evaluated on the 544 ordinary and 288 longer
held-out episodes in each precision for every arm. All three optimized variants
matched every recorded episode metric against the freshly evaluated baseline:
**4,992 matched episode comparisons, zero changed rows and zero changed
exit/death/timeout outcomes.** FP32 and AMP are compared separately; this does
not claim FP32 and AMP are identical to each other. Quality evaluations remain
synthetic 32x32 navigation scenarios, not full-size Crawl generalization.

## Profile confirmation

For five large AMP optimizer updates:

| Summed GPU kernel/operator time | Reference | Both changes |
|---|---:|---:|
| All GPU kernels | 154.78 ms | 74.04 ms |
| Explicit NCHW/NHWC conversion kernels | 33.91 ms | 0 |
| Adaptive pooling operators (forward + backward, self CUDA) | 33.66 ms | 0 |

This directly confirms elimination of the suspected work. Pooling/conversion
categories use different profiler accounting views; total kernel time is not
end-to-end wall time, and these figures should not be added to derive a new
throughput claim. The timed full-network results above include launch/optimizer
and inference overhead, hence a smaller gain than the GPU-only reduction.

Both changes are ready for use where this benchmark showed a benefit. We did
not change encoder capacity, retrain policies, implement compiled execution,
or claim a corresponding speedup for small FP32 supervised runs.
