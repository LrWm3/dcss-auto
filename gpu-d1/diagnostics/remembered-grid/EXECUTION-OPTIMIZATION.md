# Compiled encoders and CUDA graphs

This experiment preserves the symbolic-map GRU architecture and checkpoint. It
tests two independent execution changes on top of channels-last CNNs and the
identity-pooling bypass:

- Compile the encoder and policy/value heads with `torch.compile`. Leave the
  recurrent sequence in cuDNN and the rollout GRUCell eager.
- Capture training forward/backward and stateful inference in explicit CUDA
  graphs. Adam, gradient clipping, and GradScaler overflow handling stay outside
  the training graph.

`symbolic_execution.py` supplies the execution wrappers. `StaticUpdate` is a
PPO-shaped benchmark harness, not a newly integrated end-to-end PPO trainer.
`StaticInference` is usable by the existing navigation evaluator.

## Measurement

The benchmark uses full-size **80x70** input maps, 15x15 local crops, a 16x16
global map, 16 burn-in plus 16 learning steps, and four optimizer passes per
collected decision. The small configuration uses batch 256 / FP32; the large
configuration uses batch 4096 / mixed precision and prepared map inputs.
Inference uses 512 environments and includes categorical sampling. Graph
inference includes copying observations into persistent input buffers.

Reported decisions/s are **network-only estimates**, excluding simulation,
rollout collection, GAE, and minibatch assembly/copies. Prepared observations
exclude map preprocessing from the learning phase, but not from inference.
Each timing is the median of three rounds after warmup. A second sweep reverses
arm order to check order/thermal effects. Startup is excluded from steady state
and recorded separately in the JSON artifacts.

| Execution | Small FP32 decisions/s | Large mixed-precision decisions/s |
|---|---:|---:|
| Eager optimized encoder | 7,640–7,769 | 45,343–48,559 |
| Compilation only | 7,566–7,646 | 56,099–56,142 |
| CUDA graphs only | 11,268–11,359 | 50,353–50,596 |
| Compilation + graphs | **11,768–11,877** | **58,084–58,527** |

Ranges span the two order sweeps, not statistical confidence intervals. Combined
execution improves the large estimate by **21–28%** relative to the matching
eager sweep and the small estimate by **53–54%**. Large-batch optimizer time
falls from 15.60–15.69 ms to 12.91–12.99 ms. Inference improves too, although
the eager inference timing varies more between sweeps.

Compilation alone accounts for most of the large-batch gain. Graphs account for
most of the small-batch gain; compilation alone does not help that configuration.
There is therefore no universal speed multiplier to apply to other workloads.

First compiled updates took about 9–11 seconds in the first sweep; first
compiled inference took 2–3 seconds. Capture was roughly 0.12–0.24 seconds with
compilation already cached. These are process/cache-dependent setup costs:
the combined arm follows the compiled arm and reuses its compiler cache, so its
short startup is not an independent cold compilation measurement.

## Saved-policy behavior

The main and long held-out suites use synthetic **32x32** maps, not full-size
Crawl levels. Across 4,992 episode comparisons against the matching-precision
eager control, **no exit/death/timeout outcome changed**. Every FP32 episode
summary matched, as did graph-only execution in mixed precision. Mixed-precision
compilation changed route statistics in seven main and seven long episodes
(the same counts with and without graphs, 28 comparison rows total). Thus
compilation is not numerically or behaviorally bit-identical in mixed precision,
although success rates were preserved on this suite.

Main success remains 91.80% known stairs, 94.53% exploration, and 100% threat
backtracking; long success remains 77.34%, 81.25%, and 100%, respectively. These
checks establish checkpoint inference compatibility on the fixtures, not equal
learning curves after retraining or full-size navigation competence.

## Correctness and operational constraints

`check_symbolic_execution.py` compares eager with graph-only and compiled-plus-
graph execution, in FP32 and mixed precision. Checks cover changing inputs and
targets, loss, every parameter's gradient and update, changing action masks,
carried recurrent state, and episode resets. The mixed-precision test injects
an infinite loss: the scaler must skip the update, lower its scale, and recover
finite gradients on the next replay. All these checks pass.

Burn-in and learning use separate autocast contexts to avoid reusing detached
weight casts. Graph backward overwrites persistent gradient buffers: callers
must not set these gradients to `None` between replays. Parameters and graph
input storage must remain stable; new minibatch data must be copied in place.
The optimizer and scaler remain live outside capture.

Inference resets memory at episode-batch boundaries and recaptures if map/batch
shape changes. It does not currently support per-environment asynchronous
episode-reset masks. Returned graph outputs alias persistent storage and must
be consumed or cloned before the next replay. This is an optional experimental
runtime; existing training defaults are unchanged.

## Reproduction

Run with `gpu-d1/.venv/bin/python`:

```sh
python gpu-d1/diagnostics/remembered-grid/check_symbolic_execution.py
python gpu-d1/diagnostics/remembered-grid/check_symbolic_execution.py --compiled
python gpu-d1/diagnostics/remembered-grid/benchmark_symbolic_execution.py
python gpu-d1/diagnostics/remembered-grid/benchmark_symbolic_execution.py --reverse
python gpu-d1/diagnostics/remembered-grid/symbolic_execution_quality.py
```

Compilation needs matching Python development headers. On this machine they
are locally extracted under the ignored training-output directory; set:

```sh
export CPATH="$PWD/gpu-d1/learning-runs/remembered-grid/compiler-headers/extracted/usr/include/python3.12:$PWD/gpu-d1/learning-runs/remembered-grid/compiler-headers/extracted/usr/include"
```

Results are `results/symbolic-execution-benchmark.json`,
`results/symbolic-execution-benchmark-reverse.json`, and
`results/symbolic-execution-quality.json`. Quality checks reuse the original
saved GRU checkpoint; no retraining is involved.
