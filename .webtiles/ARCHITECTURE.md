# Autocrawl organization

The deployable bot remains one RC file. Keep it self-contained for WebTiles;
tests and benchmark tooling live beside it, not inside the game's Lua runtime.

## Policy versus execution

- `AUTOCrawl_ROUTE`: branch order, completion policy, rune requirements.
- `AUTOCrawl_TACTICS`: survival thresholds, ability cooldowns, berserk switches.
- `turn_spent(start_turn)`: shared synchronous action-completion check.
- `guarded_keys(keys)`: command plus Escape guards. Do not append targeting keys
  from message callbacks behind these guards.
- `survival_action(scan)`: ordered emergency actions, one successful action per
  invocation. Consumable/ability helpers own availability and retry checks.
- `combat_action(scan)`: rejected-Tab recovery, isolated-enemy handling, berserk,
  then native autofight. Red encounters retain a separate customization boundary.
- `ready()`: orchestration. Movement restrictions precede survival; then confusion,
  hazards, invisible activity, encounter handling, recovery, gear/ID, and routing.
  This ordering is deliberate and is not changed by the current refactor.

Legacy stair-survey behavior still exists for route-disabled mode. Do not delete
it or merge it into route travel without dedicated coverage. Further cleanup
can extract invisible-enemy handling and legacy progression from `ready()`.

## Fast verification

```
uv run --with lupa python .webtiles/tests/run.py
uv run --with lupa python .webtiles/tests/compare_policy.py c08ed68
/usr/bin/python3 .webtiles/bench/runner.py summary
```

The comparison checks default survival/combat command traces across HP, threat,
crowd size, statuses, inventory/ability availability, and rejected actions. It
does not simulate pathfinding, RNG, timing, or an entire game. Keep live tests
separate and label their exact commit in the benchmark records.

For a tactics experiment, prefer changing one policy setting or one decision
function at a time. Record unfavorable results too; no automatic rollback is
required. An experimental revision can remain in development without being
called an improvement on the weakest-seed metric.
