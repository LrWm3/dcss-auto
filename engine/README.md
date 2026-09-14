# Reconstructing the local Crawl fork

`crawl-local.patch` is a cumulative source patch against upstream Crawl commit
`ff61f77f9cb9bc203635fe8d9b8c73c4b5e0c7c3` from
https://github.com/crawl/crawl.git. It includes the local score commit plus
uncommitted simulator, observation, RNG, checkpoint and exploration-score work
as of this repository cleanup. `tactical-sim.h` is included in the patch.

From a fresh repository checkout, with no existing `crawl-0.35` directory:

```sh
git clone --no-checkout https://github.com/crawl/crawl.git crawl-0.35
git -C crawl-0.35 checkout ff61f77f9cb9bc203635fe8d9b8c73c4b5e0c7c3
git -C crawl-0.35 apply --check ../engine/crawl-local.patch
git -C crawl-0.35 apply ../engine/crawl-local.patch
```

Do not apply the older incremental patches on top of this cumulative patch.
Build requirements and specialized simulation flags are documented in
[the autonomous README](../.webtiles/bench/autonomous/README.md) and
[simulation benchmark](../.webtiles/bench/tactical/SIMULATION-BENCHMARK.md).
An existing modified checkout should not be overwritten by these commands.

The patch preserves source, not old executable hashes. Checkpoint replay is
engine-version-sensitive; keep the associated local binaries for old datasets.
When modifying the fork, refresh this cumulative patch (including newly added
source files), verify it applies to the pinned base, and commit it with the
corresponding Python/Lua changes. Crawl retains its upstream licensing.
