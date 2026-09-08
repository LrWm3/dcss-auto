# Fixed-seed benchmark

## Config-driven batch runner

Edit `batch.example.json`: give each experiment a unique `version` and fresh
character names. Keep the session names to reuse runner-owned finished sessions.
Paths in config are relative to the repository root. The example uses five
dedicated `codex-bench` sessions; existing manual sessions are not adopted.
An optional `tactics` object overrides existing AUTOCrawl_TACTICS values in the
snapshot only. Its exact values are retained in the manifest; the RC hash is
the hash after overrides, while the Git commit identifies the source revision.

```
/usr/bin/python3 .webtiles/bench/batch.py start .webtiles/bench/batch.example.json --dry-run
/usr/bin/python3 .webtiles/bench/batch.py start .webtiles/bench/batch.example.json
/usr/bin/python3 .webtiles/bench/batch.py watch next-experiment-v1 --timeout 1800
/usr/bin/python3 .webtiles/bench/batch.py status next-experiment-v1
/usr/bin/python3 .webtiles/bench/runner.py summary
```

`start` launches the configured games in parallel tmux sessions. It preflights
all names/sessions, snapshots the current RC, and records its hash, Git commit,
dirty flag and engine hash in `batches/VERSION/manifest.json`. Subsequent RC edits
do not alter that snapshot. Do not rebuild the engine during a batch.
The launcher and locally built Crawl executable must already exist; tmux is required.

`watch`/`status` collect matching terminal death morgues into `runs.jsonl` and
`evidence/`, using the existing progression parser. Collection is idempotent.
They also save recent terminal captures and flag unchanged screens after
`stale_seconds`. This is a **suspected stall**, not proof: advancing movement loops
can evade it. Completion messages are flagged for review, not silently counted
as verified clears. Pauses/completion require review and a dump before importing
with `runner.py record`. Missing sessions are reported, never recreated blindly.

Watch timeout or Ctrl-C leaves games running; call `watch` again to resume.
No gameplay input, forced save, or kill is sent during monitoring. A session is
reused only when the prior manifest records a verified death, the pane matches,
and its process still belongs to that character, with no remaining save and a
death or postmortem inventory screen. The matching death dump is revalidated. Otherwise
start refuses it. Start failures may leave a partial batch: inspect its manifest
and sessions; do not delete the manifest and retry blindly.

Runtime manifests/snapshots/screens are locally retained but Git-ignored;
benchmark rows/evidence should be committed after experiments. Only fixed benchmark
seeds are supported (subsets allowed); encode seeds as JSON strings.

Runner regression tests (isolated temporary files, no live games):

```
/usr/bin/python3 .webtiles/bench/test_batch.py
```

## Evaluation

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
