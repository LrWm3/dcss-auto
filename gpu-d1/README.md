A playable floor-clear task and three completed PPO learning runs are now available: see [LEARNING.md](LEARNING.md) for the fixed-layout task, [LEARNING-SLEEP.md](LEARNING-SLEEP.md) for the sleep-only ablation, and [LEARNING-V2.md](LEARNING-V2.md) for the multi-layout sleep/statistics task.

This is an executable CUDA/CPU prototype of the restricted D:1 wait workload. It includes a seeded native map export, shared simulation rules, two CUDA layouts, two schedulers, a native comparison harness, and measured benchmarks. Start with [RESULTS.md](RESULTS.md) for performance and limitations.

Everything is contained in this folder. The build does not use the repository's other simulation or training projects. The native integration modifies only a disposable copy under `native/`.

From the repository root:

```sh
make -C gpu-d1
make -C gpu-d1 test
gpu-d1/build/bench --backend warp --batch 8192 --monsters 8 --scenario mixed --steps 4096 --chunk 64 --trials 3
```

The checked-in fixture is sufficient for these commands. This machine uses CUDA 12.0, `g++-12`, and `sm_75`; override `HOSTCXX` and `CUDAFLAGS` in the Makefile when building for another installation.

One reported iteration is one world taking a 10-aut wait and resolving its monster actions through the next decision boundary or death. A death counts once. The next step restores that world's resident fixture, continues its RNG stream, and executes another live wait. Reset work is timed. Startup, table compilation, initial upload, final readback, validation, rendering, and policy inference are excluded from the simulation rate.

`--steps` is waits **per world**. `--chunk 1` launches one wait per batch per kernel, with successive launches queued without CPU readback. `--chunk 64` and `--chunk 256` perform fixed-action rollouts inside kernels. They do not measure an agent selecting a new action each turn. `--observe` writes current HP, shield-block count, and visible monster positions to a resident device buffer after every transition; it does not copy observations to the CPU.

| Option | Values |
|---|---|
| Backend | `cpu`, `thread` (thread per world), `warp` (warp per world) |
| CPU workers | `--threads 1`, `--threads 6`, etc. |
| Scheduling | Maximum-energy scan by default; `--heap` for fixed-array heap |
| Workload | `--scenario quiet`, `approach`, `combat`, or `mixed` |
| Population | `--monsters 0` through `64`; quiet always uses zero |
| Replication | `--batch`, `--steps`, `--trials`, `--seed` |
| Validation | `--selftest`, `--combat-check`, `--lifetimes` |

The player is a native XL1 Human Fighter with fixed starting defenses, scale mail, buckler, and ordinary weapon. The player only waits. The population cycles through unarmed rats, frilled lizards, goblins, hobgoblins, quokkas, and jackals. Every monster remains awake and hostile with permanent target knowledge. Larger counts are synthetic crowding stress cases on real D:1 geometry. There is no player attack, item use, progression, sound response, sleep/wandering, status effect, door, cloud, terrain mutation, ranged attack, spell, god, or special monster ability.

The Zot clock and other long-term world effects are also excluded from both the compact simulator and the native reference harness. Reported deaths are combat deaths. In particular, the quiet control can wait indefinitely.

The contact fixture begins around the player. The approach fixture begins about 18 path steps away and eventually enters combat. Mixed worlds alternate fixtures and execute different valid prefixes before timing, with independent RNG streams. All worlds share one map and one player location: this is favorable caching, not a diverse-map benchmark.

To reproduce the complete native export and validation:

```sh
python3 gpu-d1/scripts/build_native.py
python3 gpu-d1/scripts/export_fixture.py
python3 gpu-d1/scripts/native_reference.py
```

`export_fixture.py --search` repeats ascending seed selection. The chosen seed is pinned to 1057; selection changes require inspection. `compile_fixture.py` independently reconstructs static LOS from exported native ray bitsets and checks every origin/local-target pair against native output before writing `fixture.bin`.

To reproduce the timing matrix and sustained comparison, run these sequentially on an otherwise idle machine:

```sh
python3 gpu-d1/scripts/benchmark.py --stage matrix
python3 gpu-d1/scripts/benchmark.py --stage baselines
python3 gpu-d1/scripts/benchmark.py --stage launch
python3 gpu-d1/scripts/benchmark.py --stage sustained
python3 gpu-d1/scripts/benchmark.py --stage cpu12
python3 gpu-d1/scripts/environment.py
python3 gpu-d1/scripts/summarize.py
```

The matrix takes several minutes, particularly the CPU crowding cases. Sustained runs use the same 4,096 waits per world on every backend and also take several minutes. JSONL contains individual trials, activity counters, memory allocation, checksums, GPU event time, synchronized wall time, and GPU telemetry. A checksum is meaningful within its storage layout; the exact self-test normalizes layouts when comparing CPU and GPU worlds.

| File | Purpose |
|---|---|
| [src/sim.h](src/sim.h) | Shared integer rules, RNG, occupancy, routing, scheduling, resets |
| [src/bench.cu](src/bench.cu) | CUDA kernels, CPU baseline, driver, invariants, exact comparison |
| [src/native.inc](src/native.inc), [src/native_bench.inc](src/native_bench.inc) | Native exporter and independent reference adapter |
| [fixtures/manifest.json](fixtures/manifest.json), [fixtures/map.txt](fixtures/map.txt) | Fixture changes, positions, geometry verification, map |
| [SOURCES.md](SOURCES.md) | Source provenance, license, native instrumentation details |
| [WAIT_BENCH_PLAN.md](WAIT_BENCH_PLAN.md), [DESIGN.md](DESIGN.md) | Original implementation plan and broader port design |

This tests the value of compact simulation and batching for incoming melee combat. It is a starting point for a D:1 port, not support for arbitrary D:1 play.

For measured PPO performance improvements, see [PERFORMANCE.md](PERFORMANCE.md). New main-runner suites default to `--performance fast`; use `--performance reference` for the original computation path in a fresh output directory.

Latest completed ogre, optional-label and pressure-curriculum results: [OGRE-RESULTS.md](OGRE-RESULTS.md).
