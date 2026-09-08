# Three parallel route trials — 2026-09-07

Started three fresh random-seed MiBe characters concurrently using the same
unchanged `.webtiles/rcs/codex-autocrawl.rc`. The original session was untouched.
RC SHA-256 before and after:
`e41c3b824fce660badab222ede0440ae34c3fa121c69a1ae84b203992aed11c0`.

| Session | Character | Seed | Result |
| --- | --- | --- | --- |
| codex-autocrawl-test1 | CodexRoute1 | 8141049000053139570 | Stuck on D1, XL1, turn 5001; saved |
| codex-autocrawl-test2 | CodexRoute2 | 10905547362155994561 | Repeated D5/D6 route cycle, XL8, turn 9414; saved |
| codex-autocrawl-test3 | CodexRoute3 | 14313357861589110920 | Autonomous death to a wight on D6, XL8, turn 4082 |

No gameplay input was sent after character creation until a run was classified
as stuck and saved. No fixes were made during this batch.

## Evidence

CodexRoute1 repeatedly moved in the starting vault while an isolated rat was
visible. It gained no experience or gold. At turn 5001, the messages became:

```text
Really explore while Zot is near?
Okay, then.
Unknown command.
Infinite lua loop detected, aborting.
```

The final screen was unchanged for at least 30 seconds before saving.

CodexRoute2 repeatedly travelled toward D6, entered an upstairs arrival area
with `Level annotation: 1 transporter`, and returned to D5. Across samples
from about 30 to 120 seconds, displayed game time rose from 6256.3 to 9414.8
while experience stayed at XL8, 54%. It was saved after this repeated cycle
was established (the character dump records turn 9414 and 2:26 game time).
This is an observed route loop, not a frozen prompt or proof about indefinite
future behavior. Its precise cause remains to be diagnosed.

CodexRoute3's morgue confirms death, not a save or an automation pause.

## Preserved artifacts

Relative to `crawl-0.35/crawl-ref/source/`:

- `saves/CodexRoute1.cs`, `morgue/CodexRoute1.txt`
- `saves/CodexRoute2.cs`, `morgue/CodexRoute2.txt`
- `morgue/morgue-CodexRoute3-20260907-205829.txt`

Sessions test1 and test2 remain at the saved-game menu; test3 remains at the
post-death inventory screen. No characters are still playing autonomously.

Summary: **1 autonomous death, 2 stuck runs. None reached Lair or D15.**
