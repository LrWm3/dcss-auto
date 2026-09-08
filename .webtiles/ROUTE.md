# Configurable progression

Edit `AUTOCrawl_ROUTE` near the top of `rcs/codex-autocrawl.rc`.
The route controller replaces the old stair survey while enabled; combat,
resting, equipment and identification still run before route travel.

Default baseline:

1. D:1–11
2. Lair:1–5 (this checkout has five Lair floors)
3. D:12
4. Orc:1–2
5. D:13–15
6. Swamp **or** Shoals:1–3, whichever exists
7. Snake **or** Spider:1–3, whichever exists
8. Swamp/Shoals:4 and its rune
9. Snake/Spider:4 and its rune
10. Elf:1–2 (skip the dangerous Elf:3 end vault)
11. Vaults:1–4, requiring two runes
12. Depths:1–4
13. Vaults:5 and the silver rune
14. Zot:1–5, requiring three runes

This is a fixed baseline, not tactical advice for every character. The bot's
combat policy is still simplistic. The endpoint is route exploration, **not
Orb pickup/ascent or a game win**. It intentionally does not visit optional
Crypt, Slime, Abyss, Hell or Pandemonium.

Source: [February 2026 MiBe route discussion on the Crawl Tavern](https://tavern.dcss.io/t/need-advice-for-mi-be-going-to-orc-mines-for-first-time/1629).
Branch lengths, travel keys and rune names were verified against this local
0.35 source (`branch-data.h`, `l-you.cc`, `item-name.cc`, `travel.cc`).

## Stage format

```lua
{branch="Lair", from=1, to=4},
{branch="D", from=12, to=12},
{branch="Orc", from=1, to=2},
{branch="Lair", from=5, to=5}, -- example: postpone its ending
{branch="wet", from=1, to=4, rune=true},
```

`wet` resolves to Swamp/Shoals, `dry` to Snake/Spider, using discovered
entrances. A branch can occur in multiple stages. `rune=true` uses that
branch's rune, or supply a rune name string. `min_runes=N` prevents premature
travel into a rune-gated branch. Missing entrances, missing runes on an
exhausted branch, or repeatedly rejected travel stop with a specific reason.

`allow_partial=true` permits progression after Crawl reports inaccessible
places/items, unopened runed doors, or unvisited transporters. `ROUTE_STATE.done` records these as
`partial`, never `clear`. Set false for strict full-floor completion.
`skip_runed_vaults=true` adds small travel exclusions around runed doors;
disable it to retain the usual exploration behavior around optional vaults.
Existing exclusions are not automatically removed by changing this setting.

## Hooks

Define any of these globals inside the RC's Lua block:

```lua
function autocrawl_route_stage_enter(stage, branch)
  crawl.mpr("Starting " .. branch .. ":" .. stage.from)
end
function autocrawl_route_stage_complete(stage, branch) end
function autocrawl_route_blocked(reason) end
function autocrawl_route_complete() end
```

Hooks should only update policy/log state, not queue extra gameplay commands.
Progress, branch choices, completion labels and discoveries are saved with
the character via `c_save()`, not in an RC-wide table shared between games.
If materially changing stages on an existing character, reset
`ROUTE_STATE.index` deliberately; stored indices refer to the old plan.

The route regression suite is `tests/route.lua`. It verifies stage boundaries,
generated-branch selection, actual rune possession, save/load serialization
and strict versus partial completion. These are mocked API tests, not proof
that the combat bot can survive the whole route.
