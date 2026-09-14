This prototype extracts a restricted ruleset from Dungeon Crawl Stone Soup. The simulation and native adapters are distributed under GPL-2.0-or-later, consistent with [Crawl's license](../crawl-0.35/LICENSE). The original authors retain their copyrights.

The checked-in native source is `crawl-0.35/crawl-ref/source`, originally identifying itself as `0.35-a0-1-gc51f74b`. The isolated build uses a fixed `0.35-a0` release string because this containing repository is not Crawl's own Git history. [File hashes](results/native-source-hashes.json) identify the native files copied and patched for the exporter/reference driver.

| Rule or facility | Native source |
|---|---|
| Seeded generation / Human Fighter initialization | `dungeon.cc`, `ng-setup.cc`, `newgame-def.h` |
| Monster parameters | `mon-data.h`, `mon-util.cc`, `dat/mons/` |
| Native energy heap and monster reactions | `mon-act.cc`, `monster.cc` |
| Hit roll, random EV, shield test, basic monster damage | `attack.cc`, `melee-attack.cc`, `fight.cc` |
| Fractional AC/EV/SH, GDR, shield cap | `player.cc`, `actor.cc`, `item-prop.cc` |
| Regeneration and turn preparation | `player-reacts.cc`, `main.cc` |
| PCG, bounded sampling, random rounding, averaged rolls | `pcg.cc`, `random.cc` |
| Native ray LOS and bitsets | `los.cc`, `losglobal.cc`, `bitary.cc` |

`scripts/build_native.py` expresses every native patch. Only the copy under `gpu-d1/native/source` is changed. Hooks are inactive until `debug.gpu_bench` is invoked. The reference driver uses native attack primitives for the statistical oracle and native `handle_monsters(false)` for the wait baseline. It replaces the surrounding game loop with the restricted HP-regeneration/reset harness, disables messages and sound, strips monster equipment and ground items, and refreshes each monster's hostile target before acting.

The benchmark death hook deducts the actual incoming native damage, then unwinds at death. It bypasses end-game screens, saves, scoring and post-death effects. Reset clears the native pending action queue and restores monster templates. Reset and exception costs remain inside the native timing. The reference is therefore an instrumented subset of native Crawl, not unmodified `world_reacts()` or a UI benchmark.

The Zot clock (`zot.cc`, normally advanced by `player_reacts()`) and other long-term world effects are excluded in both the compact simulation and reference harness. Quiet waits do not expire, and recorded deaths are incoming-combat deaths.

Explicit compact deviations include stable actor-ID energy ties, permanent target knowledge, a static shortest-distance navigation field with a 24-node repair search, unarmed humanoid monsters, and no mutable terrain. See [the results](RESULTS.md) for measured consequences and validation limits.
