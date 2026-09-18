# Symbolic GRU optimization pass

The implementation keeps the 15x15 local symbolic/tactical observations, 16x16 global summary, 128-unit GRU, all weights, masks, actions, and 16-burn-in/16-learning sequence lengths. The model still has 229,476 trainable parameters. No navigation hints or teacher overrides were added.

## Changes

- Crop the raw byte grid before forming local categorical and tactical float tensors, rather than constructing full-level float maps and then cropping them.
- Cache global-bin indices and normalization denominators by map shape/device. Symbolic values still update from current observations every call.
- Use a fused `nn.GRU` for sequence training, sharing the original `GRUCell` parameters. Single-step inference retains the original cell. Burn-in avoids unused action heads; training batches the policy/value heads across sequence positions.
- Provide `prepare()` / `encode_prepared()` so deterministic symbolic observations can be materialized once in replay and reused during optimizer passes. Learned encoders still run and receive gradients every update. This reuse is benchmarked, not yet integrated into a full symbolic PPO collector/replay pipeline.

`symbolic_run.py --kind gru --fast` enables the equivalent FP32 preprocessing and fused sequence-training path in the supervised runner. It writes to a separate `symbolic-gru-fast` directory. The reference mode remains available; existing trained checkpoints are unchanged. The production sequence replay has either a completely valid burn-in or an all-invalid initial prefix, followed by a valid learning prefix and optional terminal padding. The fast path zeros burn-in hidden state for initial prefixes and masks padded learning losses, preserving valid-step outputs and gradients. Tests verify these assumptions on collected trajectories.

## Full-size network measurements

Uncontended Quadro RTX 5000 Max-Q, 80x70 inputs, 512-decision inference batch, four PPO-shaped optimizer passes per learning decision. All recurrent runs include 16 burn-in steps and 16 learning steps. Includes preprocessing during inference, sampling, value output, optimizer, gradient clipping and AMP scaling where enabled. Excludes simulator, observation export, rollout storage and GAE. Synthetic advantages/returns measure cost only; these are not PPO learning runs.

| Configuration | Learning batch | Optimizer ms | Inference batch ms | Network-only decisions/s |
|---|---:|---:|---:|---:|
| Reference FP32 | 256 | 20.23 | 5.69 | 3,056 |
| Optimized FP32 | 256 | 8.04 | 3.73 | 7,524 |
| Optimized AMP | 256 | 7.80 | 3.35 | 7,786 |
| Optimized AMP | 1,024 | 13.16 | 3.36 | 17,257 |
| AMP + precomputed symbolic inputs | 1,024 | 6.59 | 3.34 | 30,981 |
| AMP + precomputed symbolic inputs | 2,048 | 10.75 | 3.36 | 36,282 |
| AMP + precomputed symbolic inputs | 4,096 | 18.72 | 3.36 | 40,236 |

The same-batch FP32 implementation gain is **2.46x**. The fastest combined configuration is **13.17x** the refreshed reference, or about 14x the original 2,890/s measurement. A preceding measurement of the largest batch gave 40,501/s. Mixed precision alone is not the major improvement. Larger batches amortize launch and recurrent overhead; cached symbolic replay avoids repeated full-map preprocessing. Larger batches change update granularity and require new learning-quality validation. The 40k/s estimate is not a measured end-to-end PPO rate and cannot be directly equated with the old frontier-guided 153k/s end-to-end benchmark.

[Raw measurements](../../results/symbolic-optimization-benchmark.json). [PyTorch profiler operator table](../../results/symbolic-optimization-profile.txt). Profiling identified substantial full-map concatenation/copy work and many small recurrent matrix operations. Profiling runs and timing runs are separate; profiler overhead is excluded from the table.

## Correctness and navigation checks

Independent tests verify equivalent encodings on 32x32 and 80x70 grids, including map boundaries; unchanged parameter count; fused recurrent outputs and input/parameter gradients; and real padded-replay losses and all learned gradients. Parameter sharing prevents the fused GRU from becoming a separate learned model.

Loading the existing checkpoint through the fast implementation reproduces all FP32 main/long per-episode recorded metrics. AMP preserves every task group's success, death and timeout rate, with small differences in turns and reversals:

| Precision | Main known stairs | Main exploration | Long known stairs | Long exploration | Main/long threat success |
|---|---:|---:|---:|---:|---:|
| FP32 | 91.80% | 94.53% | 77.34% | 81.25% | 100% / 100% |
| AMP | 91.80% | 94.53% | 77.34% | 81.25% | 100% / 100% |

[Raw quality results](../../results/symbolic-optimization-quality.json). These are existing-checkpoint inference checks, not proof that new mixed-precision/larger-batch training converges identically. The FP32 replay loss/gradient check is the stronger implementation-equivalence test for the sequence training change. No new long training run was launched.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_symbolic_fast.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/optimize_symbolic.py --profile
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/optimize_symbolic.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/symbolic_fast_quality.py
# Optional future fresh supervised training:
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/symbolic_run.py --kind gru --fast
```

Remaining work before claiming a practical PPO rate is integrating prepared symbolic replay into a real PPO runner, choosing/validating minibatch settings, and measuring simulation plus learning together. Compilation, GPU graph capture, and further kernel fusion were not needed for this pass and remain unexplored.
