# Held-out RNG sensitivity sweep

`evaluate_rng_holdout.py SOURCE MODEL OUTPUT` evaluates the frozen V2 selector,
fixed pursuit without berserk, and fixed pursuit with berserk at ten predeclared
gameplay RNG offsets (1 through 10) for every encounter in the completed original
held-out evaluation. This is 42 encounters, 420 variants and 1,260 policy trials.
The original offset-zero results remain a separate reference, not silently pooled
with this sweep. No fitting, threshold tuning or deployment occurs.

All original held-out encounters currently start at full HP. The existing lab
binding sets HP to100% while advancing RNG; the runner asserts full initial HP
and verifies that every initial gameplay/feature field is unchanged. An injured
parent is rejected rather than silently healed. There are no gear, skill, XL,
attribute or resistance mutations in this sweep.

The augmentation engine must first match each encounter's original pursuit
prefix at offset zero. Every offset then has a repeated12-action replay check.
The actual frozen selector and both fixed policies run afresh from that offset.
The selector must choose exactly the same option at every offset, because RNG
is not observed. All outcomes are retained; no filtering for pursuit failures.

Each encounter gets wins, deaths and unknown outcomes out of ten for each
strategy. Missing, failed and stalled runs are unknown, not deaths. Reported
lower/upper recovery rates treat unknowns as all failures/all recoveries; these
are **not confidence intervals**. Ten consecutive stream offsets are correlated
perturbations of one scenario, not ten independent seeds. Use encounter/seed
grouping when interpreting results, and don't treat420 as independent samples.

## Evidence and disk usage

Completed private workers are losslessly packed as `worker-*.tar.gz`. Every
regular file is checksum-verified against the original before the unpacked worker
directory is removed. Original source artifacts and checkpoint cases are never
removed. Each result retains the archive location, archive hash, original worker
path and per-file hashes. Extract an archive into a separate scratch directory
to inspect the full original logs, transitions, save and death evidence.

Outcome auditing occurs before packing, and all archive hashes are rechecked at
completion. The old generic `verify_result` expects unpacked paths; use the
archive manifest when inspecting this sweep rather than calling it directly on
packed results. Raw paths in rows describe their original location inside the
archived worker. An8GiB disk safety floor prevents starting further variants if
space becomes tight; those variants are reported as unknown.

Run using `crawl-tactical-augment` and `DCSS_TACTICAL_AUGMENT=1`. Outputs include
the frozen manifest, per-family progress, coverage, per-encounter recovery rates,
summary and completion hashes. The active full run is
`artifacts/goals-character-v2-rng-holdout-v1`.

Smoke verification at `artifacts/rng-holdout-smoke-v1` passed paired RNG-offset1
replays and byte-for-byte archive checks.184 Python and13 Lua checks passed.
