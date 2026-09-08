# Follow-up fixes and validation

Updated `.webtiles/rcs/codex-autocrawl.rc` after the six-run batch:

- Skip all scroll reading while `you.silenced()` is true.
- Check known unsafe squares even outside current visibility. The D3 arrival
  corridor in CodexAutoCrawl28 contains a teleport trap, not a safe BFS route.
- Remember a failed committed stair entry and skip it on subsequent surveys.
- Retreat immediately when a survey has no safe downstairs but can return
  upstairs; do not fall through into native exploration on the same hook call.
- Use Crawl's safety check before equipping; decline delayed equipment
  changes during danger. Accept selected gear's equip-warning confirmation.
- Leave harmful clouds when possible; otherwise spend one waiting turn.
  Temporarily cloud-blocked enemies no longer trigger sealed-vault recovery.
- Add modal-menu escape guards to scroll commands.

All three suites pass: movement-lock, exploration, autonomous. Added cases
cover silence/recovery, offscreen traps, failed stair selection, immediate
survey retreat, unsafe equipment changes, cloud escape/waiting, temporary
cloud barriers, and equipment warning prompts.

Live tests reused `codex-autocrawl:0`, resuming the saved failed characters:

| Character | Original blocker | Follow-up outcome |
| --- | --- | --- |
| CodexAutoCrawl28 | Repeated D2/D3 stair survey | Escaped loop, reached XL7, died to a gnoll on D4 at turn 9248 |
| CodexAutoCrawl30 | Silenced reading loop on D2 | Escaped silence loop; later cloud/equipment/menu blockers were fixed during testing; after final reload continued without input to XL12, dying to an eight-headed hydra on D13 at turn 10765 |

These were iterative resumed-save tests, **not** six new uninterrupted runs
of the final RC. Do not reinterpret the earlier six-run results as passing.

Morgues (relative to `crawl-0.35/crawl-ref/source/`):

- `morgue/morgue-CodexAutoCrawl28-20260907-203340.txt`
- `morgue/morgue-CodexAutoCrawl30-20260907-204019.txt`

Pre-fix save backups are retained alongside this report as
`CodexAutoCrawl28.before-fix.cs.bak` and `CodexAutoCrawl30.before-fix.cs.bak`.
The session is left at CodexAutoCrawl30's post-death inventory screen.
