# Fused minGRU scan: speed, correctness, and benchmark correction

The original eager scan was hiding a recurrent-layer advantage. A custom Triton
forward/reverse scan makes minGRU recurrent forward/backward about 4.2x faster
than the eager implementation and 1.6x faster than cuDNN GRU at batch 256,
sequence length 16, with FP16 projections and FP32 recurrent state. This is not
a 1.6x whole-policy speedup: the CNNs dominate that workload.

## Corrected benchmark

Profiling exposed an AMP benchmark bug in `optimize_symbolic.workload`: burn-in
under `no_grad` and learning shared the same outer autocast context. The autocast
weight cache reused detached encoder/core weight casts during learning. Only
policy/value heads received gradients. This affected **previous mixed-precision
PPO-shaped network benchmarks**, including the roughly 40k decisions/s figures
in MINGRU.md and SYMBOLIC-OPTIMIZATION.md. Those AMP training estimates must not
be used. Historical JSON artifacts are retained for provenance, not endorsed.
FP32 supervised/DAgger training and its navigation results are unaffected.

Burn-in and learning now use separate autocast contexts. Benchmark and regression
checks require every trainable parameter to have a finite gradient. The profile
now includes convolution backward and the fused reverse scan. No actual PPO
learning run is claimed by these synthetic-loss benchmarks.

## Implementation

`mingru_scan.py` fuses gate/candidate computation and the affine inclusive prefix
scan into one kernel. Backpropagation uses one reverse scan for the state
adjoints, then computes candidate/gate/initial-state gradients. GEMM projection
remains in PyTorch. One-step rollout uses the same fused forward kernel with T=1.
It preserves the minGRU parameters and checkpoint format, with no new learned
parameters. Eager remains the default/reference; use `scan_backend='triton'` or
`symbolic_run.py --kind mingru --scan-backend triton` for the optimized backend.
The runner uses a separate output directory and records kernel source hashes.

Supported projections: FP32/FP16/BF16, with FP32 recurrent arithmetic/state. On
this Turing GPU, BF16 projections are converted to FP32 before launching because
native BF16 conversion requires newer hardware. The fused autograd function is
first-order only; higher-order derivatives are explicitly disabled. A sequence
must stay within one episode, as in the existing replay format. CUDA and Triton
are required; the eager backend remains available for CPU/FP64 or portability.

## Matched speed measurements

Quadro RTX 5000 Max-Q, PyTorch 2.6.0, Triton 3.2.0. Each timing is the median of
three rounds after warmup/compilation, no competing GPU jobs. Repeated in reverse
model order to assess timing sensitivity. Recurrent measurements include the
input projection and input/parameter/state gradients but no optimizer/CNN.

| Recurrent forward + backward | cuDNN GRU | Eager minGRU | Fused minGRU |
|---|---:|---:|---:|
| B=16, T=16, FP32 | 0.750–0.754 ms | 2.812–2.840 ms | 0.585–0.610 ms |
| B=256, T=16, AMP | 1.120–1.136 ms | 2.932–2.978 ms | 0.691–0.700 ms |
| B=16, T=128, AMP | 1.102–1.121 ms | 4.283–4.480 ms | 0.720–0.721 ms |

Whole-network: 80x70 inputs, 15x15 crop, 16x16 global map, 16 burn-in + 16 learn,
four PPO-shaped optimizer passes and inference at batch 512. Includes optimizer,
clipping/scaling; excludes simulator, GAE, and buffer costs. Large AMP batch
prepares deterministic symbolic inputs once but trains all CNN layers.

| Network-only decisions/s | cuDNN GRU | Eager minGRU | Fused minGRU |
|---|---:|---:|---:|
| FP32, learning batch 256 | 7,344–7,457 | 5,705–6,069 | 7,748–7,792 |
| AMP, learning batch 4096, prepared inputs | 25,790–26,426 | 23,815–25,020 | 26,573–26,655 |

The fused path removes the eager scan disadvantage. Against GRU the whole-policy
improvement is only about 4–6% in small FP32 batches and 1–3% in the large AMP
configuration; the latter is modest relative to timing variation.

Five profiled large-batch optimizer updates took 151.3 ms summed GPU kernel time,
of which the fused forward/backward scans used 0.238 ms (~0.16%). Projection and
CPU dispatch are additional costs. Convolution forward/backward account for
about 52% of profiler self-CUDA operator time, adaptive pooling forward/backward
about 23%. Removing the recurrence entirely would not remove these costs.

## Correctness and behavior

`check_mingru_scan.py` passes comparisons against sequential/eager recurrence:
outputs and projection/initial-state gradients across T=1,7,16,32,129,256;
non-power-of-two hidden sizes; zero/nonzero initial memory; extreme inputs/gates;
candidate branch boundary; chunk continuation including noncontiguous slices;
FP32/FP16/BF16 projections. Largest observed output difference was 2.29e-5 on
stress inputs. Additional checks cover learned projection/input gradients under
AMP, real padded replay losses and encoder/core gradients, matching Adam updates,
and the AMP burn-in regression for all three model implementations.

The saved 10k-update minGRU checkpoint gives identical recorded episode metrics
under eager and fused execution: all 832 main/long greedy episodes in FP32 and
all 832 in AMP. FP32 also matches the historical artifact. AMP is compared with
AMP, not claimed identical to FP32. No retraining was needed.

NVIDIA compute-sanitizer was attempted with its installed injection libraries
and child-process tracking, but terminated before the first instrumented API
call; memory-sanitizer validation is **not completed** on this host. Numerical,
autograd, padding/boundary and rollout checks above did complete.

## Reproduction and artifacts

On this host, Python headers were already extracted in the ignored compiler
headers directory described in PERFORMANCE.md. Set CPATH before Triton launches:

```sh
export CPATH="$PWD/gpu-d1/learning-runs/remembered-grid/compiler-headers/extracted/usr/include/python3.12:$PWD/gpu-d1/learning-runs/remembered-grid/compiler-headers/extracted/usr/include"
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_mingru_scan.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/benchmark_mingru_scan.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/benchmark_mingru_scan.py --reverse
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/mingru_scan_quality.py
```

Results: `symbolic-mingru-scan-benchmark.json`,
`symbolic-mingru-scan-benchmark-reverse.json`,
`symbolic-mingru-scan-quality.json`, and `symbolic-mingru-scan-profile.txt` in
`gpu-d1/results/`. Quality artifact records the reused checkpoint hash.
