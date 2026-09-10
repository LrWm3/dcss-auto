# Tactical transport benchmark (2026-09-09)

Experimental adapter: `fast_env.py`. Historical adapters, cases, engine binaries,
production RC and model weights are unchanged. This is an opt-in laboratory
transport, not a new trained policy or a fully headless simulator.

## Changes

- Remove Pexpect's default 50 ms pre-send delay.
- A new `crawl.tactical_emit(callback)` binding evaluates the existing complete
  rich observation under UI RNG, then writes it to a dedicated Unix FIFO.
  This preserves dump_char's protection against observation-consuming combat RNG.
- Select on the FIFO and PTY instead of polling a full character dump.
- Remove explicit boundary redraw and TB acknowledgement messages. Ordinary game
  rendering and PTY input still exist; drain rendering to avoid pipe backpressure.
- Buffer event logging: initial observation once, each next observation once.
  Retain a bounded terminal diagnostic tail instead of full screen output.
- Enforce observation sequence; timeout/unexpected exit is not a death. Death
  needs a private morgue with the matching character, seed and non-stale turn.

`derive_fast()` makes a checksummed copy of each case with explicit engine/RC
migration provenance and `training_ready=false`. Never modify a historical case
in place. The original save bytes are preserved.

## Reproduce

The new binary is `crawl-0.35/crawl-ref/source/crawl-tactical-fast`.
Its SHA256 is `1809611899eb4380dad2cbd42d9e85459d3e23d26d3c3a0ff27eb3dcdffe98c3`.
Incremental engine changes are in `engine-patches/tactical-fifo.patch`, applied
on top of the existing character-lab source (including observation UI-RNG fixes).

```sh
make -C crawl-0.35/crawl-ref/source WEBTILES=y GAME=crawl-tactical-fast -j4 crawl-tactical-fast
uv run --with pexpect python .webtiles/bench/tactical/benchmark_transport.py --mode baseline --output /absolute/new/baseline
uv run --with pexpect python .webtiles/bench/tactical/benchmark_transport.py --mode no-delay --output /absolute/new/nodelay
uv run --with pexpect python .webtiles/bench/tactical/benchmark_transport.py --mode fast --output /absolute/new/fast
```

Run modes sequentially, without concurrent simulation/training loads. Each mode
replays two fixed held-out traces twice: 25 gnoll decisions and the first 60
centaur decisions, 170 actions total. No model inference or controller decisions
are timed. Measure reset-to-first-observation separately from `step()` latency,
which includes command exchange, engine action, rich observation and event logging.
State validation and close/flush/cleanup are outside step timing. These are small
local measurements, not representative full-training throughput estimates.

Every initial and subsequent state is compared to the historical reference using
the existing rich-state canonicalizer: normalize entity ordering, omit sequence,
messages and death evidence paths; retain gameplay, inventory, geometry, rich
enemy and character features. All action sequences remain fixed across modes.

## Results

Initial measurements, actions divided by total step time:

| Mode | Actions/second | Mean startup |
| --- | ---: | ---: |
| Original | 9.46 | 4.99 s |
| Input delay removed only | 18.99 | 4.94 s |
| FIFO + reduced logging/rendering + no delay | 21.53 | 4.66 s |

The first fast measurement is 2.28x baseline; most of the gain comes from removing
the artificial delay. FIFO and logging changes together add about 13% over the
delay-only measurement. This comparison does not isolate those components
individually, and short-run variability matters.

Startup plus measured steps: 37.94 s baseline versus 26.54 s fast (1.43x).
Startup remains a large cost. JSON event logs shrink from 10.05/11.02 MB per
gnoll/centaur replay to 5.23/5.61 MB, about half. Save copies still dominate other
worker storage.

The independent final-adapter repeat measured 22.31 actions/s (2.36x baseline),
again matching all 170 actions. Startup plus measured steps was 27.45 s (1.38x
baseline). Thus report approximately 2.3x steady-state and 1.4x including reset,
not a claimed order-of-magnitude simulation speedup.

Evidence under `artifacts/`:

- `transport-baseline-v1/results.json`: original 170-action measurement.
- `transport-nodelay-v1/results.json`: 170-action delay-only comparison.
- `transport-fast-v1/results.json`: first 170-action fast measurement.
- `transport-fast-v2/results.json`: independent final-adapter repeat.
- `transport-fast-death-v1/results.json`: 69 additional candidate-policy actions,
  including a centaur death verified through its morgue. All states matched.

The unit suite passes 188 Python tests plus 13 embedded Lua regression checks.

## Limitations / next work

This is still PTY-controlled Crawl and builds the complete rich JSON observation
each decision; no feature caching, reset cache, in-process stepping or training
integration was implemented. Benchmark actions may include existing macro
actions, so an action is a harness decision, not necessarily one game turn.

The compact event schema is `initial_then_next_v1`; historical validators expect
`transitions.jsonl` and must not silently consume this new schema. A training
integration needs an explicit reader/auditor. Buffered logs are closed normally,
but an abruptly killed Python worker may lose its final buffered events; such an
incomplete run must not become training evidence.

Use one environment per worker process: launch temporarily sets a child-specific
environment variable and is not thread-safe. There is no active FIFO without
an explicitly configured private path. Fast checkpoints are not production RCs.

Next, profile rich observation construction/serialization versus engine time,
and reduce the roughly five-second reset cost (persistent workers/cached setup).
Those are more substantial steps toward per-action RL than adding more workers
to the present reset-heavy benchmark.
