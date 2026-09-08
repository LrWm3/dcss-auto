# Fixed-seed benchmark

Primary objective: maximize the **minimum route milestone reached across all
five fixed seeds**. Do not promote a change on average/best performance alone.
Report each paired seed delta as well: a higher minimum does not hide individual
regressions. Incomplete batches cannot win. Ties are not measured improvements.
This is an evaluation rule, **not an automatic rollback rule**. Keep iterating
on promising ideas even after a regression; record the result honestly and
distinguish the current experimental revision from the best measured revision.

Milestones follow the RC route, not lexical branch order. Reaching a floor is
not clearing it. `cleared_prefix` is null when not measured; historical runs
only establish reached milestones. Death, automation pause, and route completion
are distinct outcomes. A pause must never be represented as a death or win.

Seeds are strings (some exceed JavaScript's exact integer range). Combat/action
trajectories can diverge on identical seeds. One replay per version is a screening
test, not statistical evidence; repeat promising versions before promotion.

`runs.jsonl` is append-only measured data. Each run records seed, character,
version, RC hash/commit when known, reached location/rank, outcome, turns, XL,
and a copied evidence dump with its SHA-256. Historical hashes/commits must not
be invented. `runner.py summary` prints per-version minimum and per-seed ranks.

Usage from repository root:

```
/usr/bin/python3 .webtiles/bench/runner.py record --version NAME --character PLAYER --outcome death --commit HASH --rc-sha HASH path/to/morgue.txt
/usr/bin/python3 .webtiles/bench/runner.py summary
```

Commit the RC/tests before launching a batch; record that exact commit/hash for
every run. Commit results afterward. Never modify the tested RC during a batch.
Historical baseline is the five original CodexRoute10–14 runs. Existing reports
are retained as context; historical snapshots unavailable in Git cannot be
reconstructed exactly from a claimed hash.

New rows also carry UTC recording time and an optional engine binary hash.
Older rows may lack these fields. The engine hash is unavailable for historical
imports; do not substitute the current binary's hash retroactively. A reached
maximum can include shafts or detours and is an optimistic exploration metric;
use confirmed-clear telemetry for future stronger completion comparisons.
