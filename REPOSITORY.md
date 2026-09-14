# Repository and storage policy

## Git versus local data

Keep code, tests, RC files, small configs, documentation, compact result summaries
and the cumulative engine patch in Git. Keep virtual environments, executable
builds, engine checkouts, checkpoints, replay tensors and full actor trajectories
out of Git. The root `.gitignore` enforces the common exclusions.

The history contains local paths and selected conversation conclusions. It does
not contain raw Codex sessions or credentials. Review before making it public.
Do not use `git add -f` on generated artifacts. Use a separate artifact backup
or object store for models and datasets; an ignore rule is not a backup.

Before pushing, run:

```sh
/usr/bin/python3 scripts/check_repository.py
git diff --cached --stat
```

The checker inspects the Git index, rejects files over 5 MiB and obvious secret
or generated-data paths, and reports total staged snapshot size. It does not
claim to be a complete secret scanner. Existing history is not rewritten.

Enable the committed local guard in a fresh clone with
`git config core.hooksPath .githooks`. The hook requires `/usr/bin/python3`.
This guard is installed in the working checkout; normal commits run it
automatically. Hooks are not automatically enabled merely by cloning Git.

## Disk controls

Training already pauses below 20 GiB free and retains heavy representations
for the most recent eight cycles where the run protocol supports retention.
Compact results, models, snapshots and failure evidence remain preserved.
Old tactical experiments predate that mechanism and still consume substantial
space; a small Git checkout does not imply a small local artifact store.

Existing safe maintenance commands (dry-run by default):

```sh
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/autonomous/retention.py --run-dir PATH_TO_RUN
/usr/bin/python3 .webtiles/bench/tactical/compact_terminal_logs.py
/usr/bin/python3 scripts/clean_simulator_caches.py
/usr/bin/python3 scripts/compact_simulator_traces.py
```

Only pass `--apply` after inspecting targets. Never delete an entire artifacts
tree just because it is ignored. Do not remove engine binaries or snapshots
needed to reproduce a retained dataset. Do not run cache cleanup during live
simulation. Preserve a compact result and source/model provenance before
expiring heavy data. See the experimental ledger for known historical gaps.

`clean_simulator_caches.py --apply` removes only old private `saves/db` and
`saves/des` generated cache files under the two simulator artifact roots.
Shared templates, character saves, models, data, failure folders and evidence
are preserved. Unknown contents, symlinks and recently modified cache folders
are skipped. It refuses detected live simulator use of artifact paths; run only
between jobs. The audit is written under `.webtiles/bench/maintenance/`.
Caches can be regenerated from the associated engine; deleted cache bytes are
not a backup. Do not confuse private caches with the preserved shared templates.

`compact_simulator_traces.py --apply` losslessly compresses tactical worker
`transitions.jsonl` and `events.jsonl` older than24 hours. It verifies SHA256 by
reading every gzip back before deleting its exact original. Canonical datasets,
models, result summaries and general-policy replay are excluded. Historical
tools expecting the old filename require `gzip -dk PATH.jsonl.gz` first.
The per-file recovery audit is local-only under `maintenance/`; keep compact
cleanup summaries in Git rather than multi-megabyte deletion manifests.
