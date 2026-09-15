# Bounded ablation runner

From the repository root:

```sh
gpu-d1/.venv/bin/python gpu-d1/scripts/run_ring_ablations.py --dry-run
gpu-d1/.venv/bin/python gpu-d1/scripts/run_ring_ablations.py
```

The default plan trains seed 0 from scratch, sequentially:

| Variant | Change from baseline | Decisions |
| --- | --- | ---: |
| baseline | 256 training maps, width 128, remembered 11x11 ring | 30M |
| maps16 | 16 training maps | 10M |
| maps64 | 64 training maps | 10M |
| no_xy | Zero absolute player coordinates | 10M |
| no_explore | Zero exploration reward; retain visibility memory | 10M |
| known_frontier | Add frontier pointer, distances through observed floor only | 10M |
| wide256 | Hidden width 256 | 10M |

Total: 90M requested environment decisions, rounded up to complete PPO updates
(32,768 decisions each). This does not reuse previous experiment checkpoints.
Compare variants against the baseline's **10M** evaluation; its 30M evaluation
separately tests whether longer training helps.

All runs keep 40 enemies, a 1024-turn limit, sleep, original combat stats,
and existing global enemy inputs. Exploration reward is .002 per newly seen
floor tile in the 9x9 reveal area except where explicitly changed. The frontier
variant adds seven inputs; it cannot route through unknown terrain. Smaller
map sets are deterministic nested subsets, retaining the original map first.

Validation uses the same 32 held-out maps, 32 first episodes per map, sampled
and greedy actions, with fixed evaluation RNG. Scores are recorded initially,
at 1M, 3M, 10M, 30M and 100M where applicable, and at completion. The test split
is not loaded. Best policies are selected by sampled validation clear rate,
then kills; validation-selected results are not final test estimates.

Progress and completion output report cumulative `train_seconds` and average
`decisions_per_train_second`, including a total across the suite. Training time
includes simulation, observation construction, and policy optimization, with
GPU synchronization at update boundaries. It excludes setup, evaluation, and
checkpoint writes; it is not total elapsed runtime. It accumulates across
resumes and is already stored in each checkpoint, curve, and result JSON.
Compare result quality alongside both decision count and training time.

## Disk use and restart

Outputs default to `gpu-d1/learning-runs/ring-ablation-suite/`:

- `manifest.json`: immutable configuration, source and corpus hashes.
- `summary.json`: completed comparisons.
- `runs/<variant>-seed<N>/curve.json`: evaluation history, including per-map scores.
- Each run retains only `latest.pt` (policy, optimizer, RNG and live worlds)
  and `best.pt` (compact best validation policy), plus small JSON reports.
- Compiled libraries are shared between compatible variants. Static map
  tables are read from the existing corpus and never copied into checkpoints.

The default output cap is **2 GiB**, with **5 GiB free space reserved**. Writes
reserve space for both the previous checkpoint and its temporary replacement;
each latest checkpoint has a 128 MiB maximum. Checkpoints replace atomically,
and compiler temporary files are cleaned on normal exit. The runner stops
if a limit would be exceeded. It does not delete existing experiments.
External processes can still consume disk independently of these checks.

Press Ctrl-C once to stop at an update boundary. Rerun the **same command** to
resume; completed jobs are skipped. Periodic restart checkpoints are saved
every approximately 1M decisions. An abrupt kill resumes from the last saved
checkpoint. Changed source, corpus or experiment settings require a new output
directory; disk limits can be increased when resuming.

```sh
# Short end-to-end test in a separate directory (not a learning experiment).
gpu-d1/.venv/bin/python gpu-d1/scripts/run_ring_ablations.py \
  --smoke --output /tmp/ring-ablation-smoke

# Choose comparisons and use three seeds; allocate a larger output budget.
gpu-d1/.venv/bin/python gpu-d1/scripts/run_ring_ablations.py \
  --variants baseline,maps16,known_frontier --seeds 0,1,2 \
  --max-disk-gb 4 --min-free-gb 10 \
  --output gpu-d1/learning-runs/ring-ablation-three-seeds
```

Additional selectable variants: `maps1`, `maps4`, `no_ring`, `explore4`,
`gamma995`, `route_cue`, `route_awake`, `route_stack4`, `route_death5`.
The last three independently add awake inputs, four-frame history, or a -5
death penalty to the corrected route-cue setup; see
[ROUTE-COMBAT-ABLATIONS.md](ROUTE-COMBAT-ABLATIONS.md).
These are separate comparisons, not part of the
default suite. `route_cue` adds an eight-way first-step suggestion along a
shortest path through observed floor to the selected frontier.
`--steps` changes non-baseline budgets; `--baseline-steps` changes the baseline.
Runs require the existing CUDA/PyTorch environment and nvcc with g++-12.
Console output streams directly; redirecting it to a file creates a log
outside the runner's retention policy unless it is inside the output directory.

## Verification

Validated all seven smoke variants (16.3 MiB combined), completion skipping,
and a 256-map, 512-world baseline PPO update (14.5 MiB including build outputs).
An interruption at 256 smoke decisions followed by resume matched the
uninterrupted 512-decision run exactly: policy, optimizer, world state,
observations, RNG and sampled evaluation scores. Six storage tests cover
atomic replacement, interrupted writes, temporary-file accounting, size and
free-space limits, and refusing paths outside the suite. A deliberately tiny
suite budget stopped before compilation. Native wall-observation semantic
fixtures also passed with the known-frontier build.

```sh
gpu-d1/.venv/bin/python gpu-d1/scripts/test_ablation_storage.py
gpu-d1/.venv/bin/python gpu-d1/scripts/test_ablation_resume.py /tmp/ring-ablation-smoke
```

For measured PPO performance improvements, see [PERFORMANCE.md](PERFORMANCE.md). New main-runner suites default to `--performance fast`; use `--performance reference` for the original computation path in a fresh output directory.
