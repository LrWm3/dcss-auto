# PPO pipeline performance, 2026-09-15

The main ring-ablation runner now defaults to `--performance fast`. On the local Quadro RTX 5000 Max-Q, the route-cue configuration measured about **3.3× faster training** and **4× faster fixed-panel evaluation**. Rewards, observations, action semantics, PPO settings, and checkpoint tensor formats are unchanged. The fast path is also ported to `branches/ogre-v1` and `branches/ogre-metrics-v2`; see the ogre measurements below.

## Measurements

Training benchmark: restore the mature 200M seed-0 route-cue checkpoint, optimizer, live worlds, and RNG; 256 training maps, 40 enemies, 512 worlds × 64 turns/update, four PPO epochs, minibatch 4096, two 128-unit hidden layers. Two warmup updates then 12 measured updates, synchronized at phase boundaries. Each comparison starts from the same saved state. Timings exclude loading, compilation, evaluation and checkpoint writes. PyTorch 2.6.0+cu124, sm_75 native compilation. No concurrent training workloads during measurements.

| Configuration | Median seconds/update | Decisions/second |
| --- | ---: | ---: |
| Original full BFS, 128 threads/block | 0.7182 | 45,627 |
| Early-stop BFS, 128 threads/block | 0.3131 | 104,658 |
| Early-stop BFS, 32 threads/block | 0.2837 | 115,492 |
| Early-stop BFS, 16 threads/block | 0.2362 | 138,705 |
| Early-stop BFS, 8 threads/block | 0.2210 | 148,303 |
| Early-stop BFS, 4 threads/block (selected) | 0.2140 | 153,123 |
| Early-stop BFS, 1 thread/block | 0.2371 | 138,214 |

Two subsequent alternating baseline/selected comparisons reproduced **45,862–46,044** versus **152,847–153,285 decisions/second**. The original measured rollout phase was 0.635 s/update; selected 0.130 s. PPO remained about 0.077 s and GAE about 0.006 s. Four versus eight threads is a modest local tuning result, not a universal GPU default.

At these steady-state rates, 30M decisions would take roughly 11 minutes versus 3.3 minutes of training; 100M roughly 36.5 versus 10.9 minutes. These are extrapolations, not completed long runs. Actual total job time includes startup, evaluation and storage, and throughput changes with policy behavior.

Evaluation: same 200M model, sampled policy, 32 validation maps × 32 episodes, seed 900000, 1024-turn budget. Median of three runs:

| Evaluation implementation | Seconds | Clear rate | Death rate | Mean kills |
| --- | ---: | ---: | ---: | ---: |
| Original | 9.339 | 67.3828125% | 32.12890625% | 30.87890625 |
| Fast BFS/block launch | 2.648 | 67.3828125% | 32.12890625% | 30.87890625 |
| Fast plus frozen completed worlds | 2.312 | 67.3828125% | 32.12890625% | 30.87890625 |

All nine evaluations matched these outcome metrics. Raw reports live in [performance/](performance/): `bench-*.json`, `repeat-*.json`, and `eval-*.json`.

## What changed and why

Nsight Systems attributed **93.5% of GPU kernel time** to `learn::step_kernel`; the PyTorch profiler independently attributed 94.8%. This kernel includes both simulation and observation generation. Its expensive known-map BFS expanded the whole reachable seen region merely to identify the nearest frontier. The timing changes when replacing that BFS establish that this work was a major bottleneck.

With `FAST_FRONTIER` and route observations enabled, BFS stops when its first frontier is dequeued. At that point FIFO traversal has discovered the entire nearest-frontier distance layer, preserving the existing frontier-list tie break and predecessor distances needed for route backtracking. It still uses only revealed floor. When the frontier list is empty it skips traversal. The generic full-distance helper remains available.

The original one-thread-per-world launch put 512 worlds in only four blocks. `LEARN_BLOCK_SIZE=4` creates 128 blocks, distributing work more widely and reducing the impact of divergent world workloads. This wastes lanes within a warp but is faster for this kernel and batch size. The runner applies this setting only to route-cue variants, including healing and stacked observations; other configurations retain the original block size until benchmarked.

Evaluation previously continued simulating fresh episodes after a world's scored episode ended. The new optional `learn_step_active` mask skips those worlds. Policy sampling retains the full batch and fixed loop length, preserving RNG consumption for active episodes. Training still advances all worlds normally. Older native libraries remain loadable through the wrapper's regular-step fallback.

Removing per-minibatch finite checks and trying fused Adam produced no convincing end-to-end improvement, so neither was enabled. The next plausible targets are PPO dispatch overhead, cooperative/warp-level map traversal, and larger batches; these need separate measurement and, for batch changes, learning-quality comparisons.

## Validation and scope

- 1,200 turns × 8 CPU worlds: original versus selected library observations, masks and transition outputs match.
- Inactive-world test: state and buffers stay unchanged; active worlds match ordinary stepping.
- Route fixtures pass: detours, unknown shortcuts, direct/adjacent routes, at-goal, unreachable and absent targets.
- GPU fixed-panel evaluation matches across both implementations and the active-mask path.
- End-to-end smoke runs pass for route cue, one heal charge, and four stacked observations.
- Interrupted four-frame training resume exactly matches uninterrupted model, optimizer, world state, observations, masks, RNG and sampled evaluation. Frame ordering/reset tests pass.

This is a measured implementation improvement, not evidence of improved learning or sample efficiency. No new long learning experiment was run. Existing result directories and checkpoint files are preserved; the runner's source/manifest checks still require a fresh output directory after source changes. Fast mode is recorded in job manifests and library names; `--performance reference` selects full BFS, original block size and ordinary evaluation stepping for fresh comparison runs.

## Reproduction

Run from the repository root. Benchmark scripts default to the existing 200M checkpoint and shared corpus. The optimized library can be built by a smoke run:

```sh
gpu-d1/.venv/bin/python gpu-d1/scripts/run_ring_ablations.py --variants route_cue --smoke --output /tmp/route-perf-check
gpu-d1/.venv/bin/python gpu-d1/scripts/benchmark_pipeline.py --output /tmp/baseline.json
gpu-d1/.venv/bin/python gpu-d1/scripts/benchmark_pipeline.py --library /tmp/route-perf-check/build/ring-reward2-frontier1-route1-fast.so --output /tmp/fast.json
gpu-d1/.venv/bin/python gpu-d1/scripts/benchmark_evaluation.py --library /tmp/route-perf-check/build/ring-reward2-frontier1-route1-fast.so --active --output /tmp/evaluation.json
```

`benchmark_pipeline.py --torch-profile` writes a bounded Chrome trace and operator table; `--nsys` brackets measured updates with the CUDA profiler API. The saved Nsight baseline used:

```sh
nsys profile --trace=cuda,nvtx --sample=none --cpuctxsw=none --capture-range=cudaProfilerApi --capture-range-end=stop --force-overwrite=true -o gpu-d1/performance/nsys-baseline gpu-d1/.venv/bin/python gpu-d1/scripts/benchmark_pipeline.py --warmup 2 --updates 2 --nsys --output gpu-d1/performance/profile-baseline.json
```

The local 2022.4 Systems importer needed a private `libssh.so` symlink to the installed `libssh.so.4` and that directory in `LD_LIBRARY_PATH`; no system libraries were changed. Summary report: [nsys-baseline-stats.txt](performance/nsys-baseline-stats.txt). Profiler timings are excluded from throughput comparisons. The first Nsight Compute section-based captures reported no metrics. An explicit counter request succeeded: the selected kernel used 128 blocks of four threads, with 6.21% active warps relative to peak in one captured step. That narrow sample suggests remaining parallelism opportunities; it does not establish a new bottleneck or expected speedup. See [counter export](performance/ncu-explicit-metrics.csv). All Compute-instrumented throughput timings are excluded from performance comparisons. Reproduce with `ncu --metrics gpu__time_duration.sum,sm__warps_active.avg.pct_of_peak_sustained_active,dram__bytes_read.sum --kernel-name regex:step_kernel --launch-count 1 --target-processes all` followed by the benchmark command.

The profiling directory was about 37 MiB before the final counter capture. Benchmark scripts write summaries and bounded traces, not checkpoints or trajectories. Large binary profiler artifacts and local libraries are ignored by Git.

## Ogre rollout and repository-wide port

Both ogre branches now use the same fast BFS and block launches as the main runner, with masked stepping during evaluation. All three `run_ring_ablations.py` entry points default to `--performance fast` and accept `--performance reference`. Native route builds also default to fast even when compiled directly or through older scripts; `-DREFERENCE_PERFORMANCE` opts out. Unrelated observation tasks retain the original 128-thread default. Legacy floor-clear wrappers and their shared evaluator now support masked stepping, with a fallback for older compiled libraries.

At the stopped two-ogre seed-0 checkpoint (55,607,296 decisions), eight measured PPO updates after two warmups gave:

| Two-ogre configuration | Seconds/update | Decisions/sec |
| --- | ---: | ---: |
| Original | 0.6593 | 49,699 |
| Fast | 0.2323 | 141,059 |

This is a **2.84×** short-benchmark speedup. Fixed-panel evaluation dropped from 9.192 to 2.178 seconds (one comparison per implementation). All 1,024 individual terminal output vectors and returns matched, including accumulated wake events, adjacency and proximity counters. Original-vs-fast trajectories also passed 8,400 world-turn checks on CPU/CUDA. Raw artifacts: `performance/ogre2-{reference,fast}.json`, `results/ogre-fast-{parity,evaluation}.log`.

The unfinished continuation was stopped through SIGTERM at an update boundary, then forked into `learning-runs/ogre2-baseline-150m-fast`. The old directory remains intact. The migration preserves weights, optimizer, live worlds, observation buffers, RNG, history and accumulated training time. A provenance file records the old checkpoint hash and boundary; only performance metadata changes. `scripts/migrate_performance_suite.py` performs this explicit migration under the source suite's lock rather than weakening source/manifest checks. It refuses finished runs and existing destinations.

Training timing in the migrated result is cumulative across the original and fast phases; use the migration boundary to calculate fast-phase throughput. The earlier uninstrumented and instrumented 30M histories remain in the curve. The training target remains 150M total decisions and the next scheduled evaluation is 75M.

Port validation also passed zero-, one- and two-ogre CPU/CUDA parity with spawn-distance and role-bit checks, three original-branch smoke runs, instrumented two-ogre smoke training, and an interrupted instrumented resume. Explicit migration comparison found identical model/optimizer/world tensors, RNG, history and timing at 55,607,296 decisions.
