# Terminal log compaction

`compact_terminal_logs.py` compacts only `artifacts/**/worker-*/terminal.txt`
files older than one hour, at least 64 KiB, not symlinks, not open by a visible
process, and without an existing `.gz` sibling. Run between benchmark batches.

It retains checkpoints, RCs, action traces, model files, character dumps, death
morgues and pre-existing evidence archives. Active games are not stopped.

```sh
python3 .webtiles/bench/tactical/compact_terminal_logs.py
python3 .webtiles/bench/tactical/compact_terminal_logs.py --apply
```

Each new gzip archive is decompressed and SHA256-checked before removing its
exact uncompressed source. A JSONL manifest records source path, archive path,
original SHA256 and before/after byte counts. The manifest is under `artifacts/`
with a `terminal-compaction-` prefix. Failed verification keeps the original.

To restore a particular log at its historical path:

```sh
gzip -d /absolute/path/to/worker-example/terminal.txt.gz
```

Historical diagnostics which read `terminal.txt` directly need this restoration;
the historical adapters are intentionally not modified to read gzip. Source bytes
are recoverable exactly; file timestamps are not guaranteed to be restored.
