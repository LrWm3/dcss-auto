# Source optimizations, cache reuse and process scaling — 2026-09-10

Recommended **experimental** configuration: six independent process workers,
`crawl-tactical-sim`, `DCSS_TACTICAL_SIM_FLAGS=3`, and `CachedEnvironment` with a
verified private-copy cache template. Production RCs, historical adapters,
historical engine binaries and model weights are unchanged. No training started.

## Measurements

The scaling workload is fixed: six repetitions each of a 25-action gnoll trace
and a 60-action centaur prefix, **510 actions in 12 resets per configuration**.
Each worker runs one independent Crawl process at a time. Groups run sequentially
on the same six-physical-core / twelve-logical-CPU machine, without simultaneous
builds or training jobs. Existing unrelated background services were not stopped.

| Workers | Uncached batch | Cached batch | Cached actions/s |
| ---: | ---: | ---: | ---: |
| 1 | 79.31 s | 27.36 s | 18.64 |
| 2 | 43.70 s | 14.64 s | 34.84 |
| 4 | 24.95 s | 8.32 s | 61.31 |
| 6 | 18.68 s | 6.40 s | 79.73 |

Independent six-worker cached repeat: **6.87 s, 74.19 actions/s**. Thus the combined
parallel/cache gain is about **11.5–12.4x** relative to one uncached worker with the
same source flags, on this short-reset-heavy workload. Parallelism alone gave
4.25x. These are aggregate batch rates, not single-instance simulation speed.

Mean reset-to-observation latency was 4.66 s uncached versus 0.42 s cached with one
worker; at six workers it was 6.56 s versus 0.51 s. Cache preparation is a one-time
cost excluded from batch timing; verification and private per-reset copies are
included. Each cache template contains only compiled game data, not a save.

Source-only ablation, two replays / 85 actions per setting:

| Flags | Changes enabled | Single-worker step actions/s |
| ---: | --- | ---: |
| 0 | FIFO engine, presentation unchanged | 22.93 |
| 1 | Suppress explicit delays | 29.04 |
| 2 | Suppress final dungeon rendering / screen refresh | 22.42 |
| 3 | Both | 30.87 |

Delay removal accounts for most of the source-level gain. Rendering alone did
not demonstrate a gain; the modest difference between flags 1 and 3 needs more
repetitions before attributing it to rendering. The larger flags-3 serial runs
measured 29.16–31.48 step actions/s. Step rate excludes startup and validation;
the batch table includes process-pool startup, input loading, validation, logging,
reset, child close and pool shutdown. Do not compare these two rates as equivalent.

## Implementation and fidelity

- `engine-patches/tactical-simulation.patch` is a **combined replacement** for
  `tactical-fifo.patch`, applied to the existing character-lab source. It includes
  the FIFO binding plus new `tactical-sim.h`, `view.cc` and `libunix.cc` changes.
  Do not apply both FIFO and simulation patches to the same base.
- New binary: `crawl-0.35/crawl-ref/source/crawl-tactical-sim`, SHA256
  `03e2bab7becee67c6133e6c1390027d7dcdd06750348f76d5c8f9d3b4b180a1b`.
- Flags activate only after the first FIFO observation callback. Startup UI is
  retained. Map visibility, `show_init`, stash tracking and `player_view_update`
  still run; this is not a blanket removal of `viewwindow` and not fully headless.
- The Lua throttle's instruction/error checks remain; delay suppression only
  bypasses its sleep when that path is used. No gameplay RNG advancement changed.
- `cached_env.py` copies only the worker's `saves/db` and `saves/des`. Source
  inspection found those caches otherwise rebuilt in each new private save dir.
  Template hashes and engine hash are checked. Per-worker copies are writable
  and independent, so stale-cache regeneration cannot modify another worker.
- Source files and cache validity are still checked by Crawl's normal loader.
  Rebuild the template when changing engine/data. Use a completed worker to make
  the template. The template does not make arbitrary historical states compatible.
- `benchmark_simulation.py` uses spawned Python processes, not threads. It stores
  engine/adapter provenance, per-trial state hashes, CPU/step/reset timings and a
  snapshot of the benchmark source. All derived cases remain training_ready=false.

Every initial and next gameplay state was compared to the historical rich
reference through the existing canonicalizer (same exclusions as the prior FIFO
benchmark: messages, sequence, death-path provenance and entity ordering).
This is repeated testing of **two encounter families**, not broad coverage of all
Crawl prompts, actions, clouds, branches or monsters. Full observations and death
evidence are retained in the workers; no benchmark outcomes were used for fitting.

Across all groups, **5,344 actions in 128 replays matched**, with no divergence or
stall. Six centaur death morgues were SHA256-verified again after process close.
All 575 cache-template files retained their original hashes after concurrent
trials. The full suite passed 191 Python tests plus 13 embedded Lua checks,
including new cache corruption, wrong-engine and private-copy isolation tests.

## Reproduce

```sh
make -C crawl-0.35/crawl-ref/source WEBTILES=y GAME=crawl-tactical-sim -j4 crawl-tactical-sim
uv run --with pexpect python .webtiles/bench/tactical/benchmark_simulation.py --output /absolute/new/uncached --flags 3 --workers 1 2 4 6 --jobs 12
uv run --with pexpect python .webtiles/bench/tactical/cached_env.py --engine crawl-0.35/crawl-ref/source/crawl-tactical-sim --worker /absolute/completed/worker --output /absolute/new/template
uv run --with pexpect python .webtiles/bench/tactical/benchmark_simulation.py --output /absolute/new/cached --flags 3 --workers 1 2 4 6 --jobs 12 --cache-template /absolute/new/template
```

Artifacts under `artifacts/`: `simulation-ablation-v1`, `simulation-scaling-v1`,
`simulation-cache-v1` (template), `simulation-cache-scaling-v1`,
`simulation-cache-repeat-v1`, `simulation-cache-death-v1`.

## Next bottleneck

Reset cost is now much smaller without needing checkpoint forking. Each decision
still builds a large Lua/JSON rich observation and uses PTY input. Profile and
optimize observation construction/encoding next, then integrate the explicit
compact-event auditor and per-action training loop. Keep process-level isolation;
do not attempt to multithread one Crawl game. Native batched stepping / checkpoint
forking remain future options, not implemented features of this benchmark.
