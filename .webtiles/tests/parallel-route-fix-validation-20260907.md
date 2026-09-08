# Stuck-save regression validation — 2026-09-07

Updated RC: `../rcs/codex-autocrawl.rc`.

## Causes and changes

- Isolated-monster exploration oscillated between custom frontier movement and
  native exploration. Keep custom exploration active for that floor until its
  frontiers are exhausted; prioritize stepping into adjacent unknown terrain.
- Zot's exploration confirmation required the synchronous `c_answer_prompt`
  hook, not keys queued from a message callback.
- An unvisited transporter prevented route completion, causing D:5/D:6 cycling.
  Record this native exploration result as **partial**, accepted only when
  `allow_partial` is enabled; do not claim full clearance.
- On Lair:1, all eight adjacent squares were travel-excluded despite being
  traversable floors. Add a bounded terrain-checked path out of an exclusion
  pocket. Continue rejecting monsters, unsafe cells, traps, and runed doors.
  Approve only the confirmation for the deliberately selected exclusion step.

## Same-character live validation

The existing tmux sessions and failing characters were reused, with save/reload
between RC revisions. No manual combat was performed.

| Character | Original failure | Observed outcome |
| --- | --- | --- |
| CodexRoute1 | D:1 isolated rat/frontier oscillation, then Zot prompt | Escaped starting area; died of gnoll poison on D:4, XL6, turn 8462 |
| CodexRoute2 | D:5/D:6 transporter-related route loop | Passed D:6, reached Lair; escaped the Lair:1 exclusion pocket, traversed Lair through Lair:5, returned to D:12, died to a titanic slime creature, XL14, turn 20166 |

Morgues under `crawl-0.35/crawl-ref/source/morgue/`:

- `morgue-CodexRoute1-20260907-210621.txt`
- `morgue-CodexRoute2-20260907-211242.txt`

Pre-fix save backups remain here as `CodexRoute1.stuck.cs.bak` and
`CodexRoute2.stuck.cs.bak`.

## Limits

These are iterative resumed-save tests, not fresh uninterrupted runs.
CodexRoute2 also stopped in a read-item menu on Lair:2; Escape dismissed it,
after which it progressed to its natural death. That separate modal-input
issue remains unverified/unfixed. The original movement and route failures
are resolved on these saves, but fully intervention-free reliability is not
established. CodexRoute3's prior natural death was not rerun.

All four mocked Lua regression suites passed after the final patch:
movement-lock, exploration, autonomous, and route. Added coverage includes
frontier stickiness, Zot confirmation, transporter partial completion, and
one-use exclusion confirmation with hazard rejection.
