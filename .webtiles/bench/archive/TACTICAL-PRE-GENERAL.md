# Tactical Crawl system archive

This file marks the boundary between the scenario-specific Crawl experiments and
the general policy-training system.

## Frozen baseline

The last tactical-only repository state is preserved as the local Git tag:

```text
archive/tactical-pre-general-v1 -> 6a43cd3
```

That state contains the MiBe automation controller, chained encounter
benchmarks, berserk policies, RNG-offset runs, and the fast tactical transport.
The important source and benchmark paths are still present at their original
locations so old results remain reproducible:

* `.webtiles/rcs/codex-autocrawl.rc`
* `.webtiles/bench/tactical/`
* `.webtiles/bench/CHAIN-BENCHMARK.md`
* `.webtiles/bench/CHAIN-OFFSETS.md`
* the existing tactical simulator patches and build artifacts

The old files are intentionally not moved or deleted: existing checkpoints and
benchmark scripts refer to those paths. New development must not add tactical
rules to that controller. Those benchmarks are now regression and
interpretability fixtures for the general policy.

## New system

The general training implementation lives in `.webtiles/bench/autonomous/`.
It owns the structured observation, variable legal-action interface, replay,
behavioral-cloning bootstrap, autonomous actors, counterfactual evaluation,
and champion/challenger orchestration.

To compare work against the old system, check out or inspect the archive tag;
to run new training, use the autonomous run directory and its persisted
`latest_status.json`.
