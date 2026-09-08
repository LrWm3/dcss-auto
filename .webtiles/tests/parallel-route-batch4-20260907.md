# Five parallel fresh trials — 2026-09-07

Reused test1/test2/test3 and added test4/test5. Characters were fresh random-seed
Minotaur Berserkers with hand axes. No gameplay input was sent after startup.
The original non-test session and existing saved characters were untouched.

Production RC SHA-256 before and after:
`23bb6944da3a34bd0461da7df08e71758b8ff2004dd54b115c2b0e842617a7d0`.
No RC changes were made during testing.

| Character | Seed | Natural death | XL | Turns |
| --- | --- | --- | --- | --- |
| CodexRoute10 | 6144198052690956201 | D:4, crimson imp summoned by Eustachio | 4 | 1216 |
| CodexRoute11 | 13772526223844354029 | D:7, orc priest's divine providence | 9 | 4937 |
| CodexRoute12 | 1760771545328102746 | D:7, killer bee | 9 | 6004 |
| CodexRoute13 | 17908030050512890810 | D:6, electric eel | 8 | 4920 |
| CodexRoute14 | 103583508244309201 | D:11, sun demon summoned by a kobold demonologist | 11 | 8884 |

**Five autonomous deaths, zero observed stalls, zero D:15 clears.**
These short runs do not establish reliability in later branches.

CodexRoute14 was observed wearing the +6 chain mail of Heasu
`{rPois rC++ Int-4 Dex+3}` with Intelligence 0 and Crippled/Slow status on D:7.
It continued to D:11, so this was not a stall, but it exposes a harmful
gear-selection decision. No attempt was made to fix it in this test-only batch.

Morgues under `crawl-0.35/crawl-ref/source/morgue/`:

- `morgue-CodexRoute10-20260907-212813.txt`
- `morgue-CodexRoute11-20260907-212844.txt`
- `morgue-CodexRoute12-20260907-212831.txt`
- `morgue-CodexRoute13-20260907-212823.txt`
- `morgue-CodexRoute14-20260907-212843.txt`

All five test sessions remain at their post-death inventory screens.
