# Three fresh trials, batch 2 — 2026-09-07

Reused tmux sessions `codex-autocrawl-test1`, `test2`, and `test3` with fresh
random-seed Minotaur Berserkers. The original session was untouched.
RC SHA-256 before and after:
`21d010fc038b9a7d23e82c441a7af3d88941eacacd95b29e5b9a84d1fce3b8b0`.

| Character | Seed | Result |
| --- | --- | --- |
| CodexRoute4 | 10227854427752258448 | Natural death to a gnoll on D:4, XL4, turn 2617 |
| CodexRoute5 | 10294902866757476507 | Stuck in a repeating exploration loop on D:6, XL9 40%; saved at turn 8921 |
| CodexRoute6 | 13300319539782545459 | Stuck at a read-item menu; saved on Lair:2, XL12 43%, turn 13015 |

No gameplay input was sent after startup until a character was classified as
stuck. No RC changes or fixes were made in this batch.

## Evidence and preservation

CodexRoute5 repeatedly appeared at the same D:6 position near an isolated angel.
Messages included `The angel shouts!`, `Done exploring.`, and `Unknown command.`
Displayed game time rose from 6361.0 to 7811.0 to 8935.0 across samples without
depth or XP progress. Displayed time is not identical to the dump's turn count.
Saved with Ctrl-S after classifying the loop. Its precise controller cause was
not diagnosed during this test.

CodexRoute6 progressed through D:11 into Lair. It then remained at the identical
`Read which item?` menu for more than 30 seconds. Only after classifying it as
stuck, Escape and Ctrl-S were sent to preserve the character. The resulting
dump places it on Lair:2. This reproduces the modal-input failure seen during
the preceding validation, without manual intervention before the failure.

Artifacts relative to `crawl-0.35/crawl-ref/source/`:

- `morgue/morgue-CodexRoute4-20260907-211542.txt`
- `saves/CodexRoute5.cs`, `morgue/CodexRoute5.txt`
- `saves/CodexRoute6.cs`, `morgue/CodexRoute6.txt`

Session test1 remains post-death; test2/test3 are at the saved-game menu.
Result: **one autonomous death, two stuck runs; none cleared D:15.**
