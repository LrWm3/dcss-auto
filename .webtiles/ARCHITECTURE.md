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
- `observe_encounter(scan)`: persistent, non-action encounter state: idle,
  prepare, fight, disengage, recover. Tracks recent danger, unseen activity,
  HP loss, peak group size and retreat budget across LOS interruptions.
- `manage_encounter(scan)`: executes preparation, bounded retreat, or recovery;
  otherwise delegates to the existing combat/invisible-activity helpers.
- `ready()`: observes the encounter and attempts emergency resources before the
  movement-restriction gate; then confusion, hazards, encounter management,
  invisible activity, combat, recovery, gear/ID, and routing. Thus an immobile
  or unseen-threat situation need not bypass non-movement emergency resources.

Encounter control is selectable with `encounter_control=false` for comparison.
Recovery uses `berserk_recovering()` including the actual `on berserk cooldown`
status: Crawl tracks this separately from exhaustion and slow. Native exploration
stops on smart pickups so safe gear/ID hooks can run before the next encounter.
`early_commit` remains an optional low-XL override, disabled after its first
five-seed trial regressed. Known fear scroll use confirms the area preview before
Escape guards; the preview is not an ordinary directional attack target.

## Remembered invisibility-capable caster

The encounter retains one priority caster's name/threat after LOS loss, based on
the visible spellbook's Invisibility spell. It expires after quiet turns, resets
on floor change, and clears on a confirmed kill message. Other visible monsters
do not erase the missing caster. This is bounded single-threat memory, not a
complete monster tracker; loss of LOS is conservatively treated as possible
invisibility, not proof of it. Relative coordinates are not retained as targets.

Proactive Trog's Hand has a two-use-per-floor budget; emergency uses retain their
normal checks. Low-level visible casters suppress generic berserk. A remembered
caster can instead trigger a direct commitment only while visible and adjacent,
HP>=40%, at most four visible foes, and no berserk/cooldown. Adjacent priority
caster attacks precede generic Tab targeting. Safe closure of a two-tile gap
avoids retreating repeatedly inside potential polearm range.

Unmarked blind probes have a three-attempt budget. Marked adjacent disturbances
can be attacked; marked disturbances two tiles away may be approached. With no
target, bounded known-upstairs withdrawal is attempted only when movement is
available and not slowed/exhausted/on berserk cooldown. Otherwise the bot waits
and rechecks resources; this remains weak when trapped without usable resources.
The first version uses a short threat memory and logs phase transitions. Retreat
only increases distance on known safe terrain with no adjacent melee attackers;
it is not a full cover/path planner or stair-escape strategy. Crowd berserk needs
multiple adjacent foes and a bounded visible group. Yellow/red triggers remain.

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
