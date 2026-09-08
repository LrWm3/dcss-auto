# Death analysis and resilience replays — 2026-09-07

## Evidence from the original five deaths

- CodexRoute10 died during berserk cooldown against Eustachio's summons.
- CodexRoute11 died surrounded and poisoned with fear, haste and Trog abilities
  available but unused.
- CodexRoute12 died berserking with four heal-wounds and four curing potions.
  The controller had no emergency consumable policy, and berserk prevented use.
- CodexRoute13 pursued an eel through water after berserk, taking lightning
  while slowed. Fog, teleportation, and Trog's Hand went unused.
- CodexRoute14 equipped Int-4 armour, reaching Intelligence zero, and died
  slowed and burning against summoned demons with healing/escape supplies left.

## Implemented changes

- Identified curing for dangerous poison, heal wounds below 45% HP,
  teleportation/fear below 55%, haste/might in threatening fights.
- Use Crawl's actual `about to teleport` status to avoid cancelling a pending
  teleport by reading another scroll. Reject scroll actions while confused or
  silenced, and all consumables while berserk. Same-turn rejection guard.
- Trog's Hand below 80% HP with an adjacent hostile, subject to availability,
  active regeneration, and a 40-turn retry interval.
- Brothers in Arms below 70% HP against groups or red threats, with a 20-turn
  retry interval. Failed invocations that spend a turn still end the action.
- Berserk at 55%+ HP for adjacent yellow/red threats or groups of three or more.
  A first draft restricted berserk to small groups and performed worse; removed
  that restriction and reduced excessive Trog's Hand usage before the second batch.
- Reject known negative artefact stat modifiers that would leave a stat at one
  or lower; remove already-equipped offending gear when safe. This is a safety
  gate, not a complete resistance-aware equipment optimizer or multi-item planner.
- Use `you.turn_is_over()` to stop after synchronous consumable use; the displayed
  turn counter can lag command execution. Apply the same guard to the existing
  invisible-enemy attack fallback to prevent a second command on a spent turn.

API behavior checked against the local Crawl source, including l-you.cc,
l-item.cc, artefact.cc, and duration-data.h. All five mocked Lua suites pass:
movement-lock, exploration, autonomous, route, survival.

## Same-seed second replay results

Five existing test sessions reused, fresh characters, no manual gameplay after
startup. Each used its corresponding original seed. Same seed does not guarantee
the same action trajectory or combat rolls after controller changes.

| Seed | Original | Second replay | Character |
| --- | --- | --- | --- |
| 6144198052690956201 | D:4 death, XL4 | Lair:2 death, XL12, petrified by basilisk then killed by alligator; turn 11498 | CodexResilient6 |
| 13772526223844354029 | D:7 death, XL9 | D:2 death, XL3, Robin's goblin; turn 532 | CodexResilient7 |
| 1760771545328102746 | D:7 death, XL9 | D:7 death, XL9, wyvern; turn 6804 | CodexResilient8 |
| 17908030050512890810 | D:6 death, XL8 | D:11, XL11, paused: travel to Lair:1 made no progress; saved | CodexResilient9 |
| 103583508244309201 | D:11 death, XL11, Int0 | D:10 death, XL11, gnoll sergeant; turn 9620, Int4 and dangerous armour unequipped | CodexResilient10 |

Observed live: CodexResilient8 used heal wounds; CodexResilient10 retained Int4
and left the Int-4 chain mail unequipped. CodexResilient9 progressed despite
extra-command Lua errors in invisible-enemy handling, then paused at Lair travel.
That action-check error was fixed after the batch; the final small guard patch
has regression coverage but was not followed by another full five-seed replay.

Result: two seeds reached farther, one died on the same floor, two died earlier.
Four natural deaths and one routing pause. No claim of an overall win-rate
improvement follows from this small, mixed sample. All deaths were natural;
only saved the paused run after its terminal automation message.

The first draft (CodexResilient1–5) produced D:2, D:2, D:3, a D:11 missing-Lair
entrance pause, and D:6 respectively. Its surviving character CodexResilient4
is also saved. These initial regressions motivated the second draft.

## Artifacts

Production RC: `.webtiles/rcs/codex-autocrawl.rc`.
Final SHA-256: `f3bb81f248a51a0ae0e066fe0093aa41b2021971eaa80854e5bbfef4d1ac32b0`.
Morgues and saved dumps: `crawl-0.35/crawl-ref/source/morgue/`, named
`morgue-CodexResilient*-20260907-*.txt` and `CodexResilient4.txt` /
`CodexResilient9.txt`. Saves: `saves/CodexResilient4.cs` and
`saves/CodexResilient9.cs` under the same source directory.

Remaining priorities: early swarm positioning, using ranged resources against
eels/casters, petrification response, extinguishing liquid fire by movement,
and diagnosing the newly exposed Lair travel failure. Original unrelated
sessions were untouched. No test character remains playing autonomously.
