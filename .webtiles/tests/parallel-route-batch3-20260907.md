# Fix verification and three fresh runs — 2026-09-07

Final RC SHA-256:
`23bb6944da3a34bd0461da7df08e71758b8ff2004dd54b115c2b0e842617a7d0`.

## Fixes

- An unsafe cloud anywhere in the known map previously made combat wait when
  no enemy was reachable, including permanent clouds in isolated vaults.
  Now a hypothetical BFS must show that removing the cloud barrier actually
  connects the player to an enemy before choosing that wait.
- On a completed floor, route progression precedes isolated-monster handling.
  Partial completion is accepted only when the configured policy allows it.
- Blink target keys were appended behind the blind-read Escape guards. After
  cancellation, leaked `r` target-centering input could become a fresh read
  command. Blind-read blink now uses the existing Escape guards, with
  synchronous `c_answer_prompt` cancellation and no appended target keys.

## Reproduction verification

Preserved original failing saves in `CodexRoute5.stuck.cs.bak` and
`CodexRoute6.stuck.cs.bak` before testing. Existing tmux test sessions were
reused; no manual combat was performed.

- CodexRoute5 left its D:6 angel stall and died on D:7, XL9, turn 9435.
  Repeated from the same backup with the final cloud-aware patch: same result.
  Morgue: `morgue-CodexRoute5-20260907-212305.txt`.
- CodexRoute6 resumed on Lair:2 and died naturally on Lair:3, XL12,
  turn 14671. Morgue: `morgue-CodexRoute6-20260907-212209.txt`.
  This save had already consumed the unknown blink scroll, so resumption alone
  does not reproduce the modal-input trigger.
- Replayed seed 13300319539782545459 from character creation as CodexBlinkReplay.
  It died on D:11 without stalling, but still held an unknown blink scroll, so
  this replay also did not exercise that trigger.
- Therefore restored the preserved CodexRoute6 save for a controlled engine
  check using `blink-input-check.rc` (includes production RC, pauses ready).
  In the Lua console ran `BOT.blind_pending=true;
  crawl.process_keys("rb\027\027\027")` using its known blink scroll.
  Crawl displayed `Blink to where?`, then `Okay, then.`, and returned to the
  map without a read-item menu. This directly checks the same targeter and
  queued-input interaction, but uses a known scroll rather than a new blind ID.
  The diagnostic character was saved afterward; the untouched backup remains.

## Three fresh random-seed trials

All three used the final unchanged RC and existing test1/test2/test3 sessions.
No gameplay input was sent after startup, and no fixes were made during them.

| Character | Seed | Outcome | Turns |
| --- | --- | --- | --- |
| CodexRoute7 | 1040932820120213258 | Died to a summoned marrowcuda on D:6, XL8 | 5496 |
| CodexRoute8 | 1557824207897580629 | Died to a two-headed ogre on D:7, XL9 | 4915 |
| CodexRoute9 | 12600079611153054637 | Died to an orc priest on D:3, XL4 | 1817 |

Morgues under `crawl-0.35/crawl-ref/source/morgue/`:

- `morgue-CodexRoute7-20260907-212454.txt`
- `morgue-CodexRoute8-20260907-212458.txt`
- `morgue-CodexRoute9-20260907-212444.txt`

**3 autonomous deaths, 0 observed stalls. None cleared D:15.** These short
runs do not establish later-branch reliability or strong survival performance.
All four Lua regression suites pass: movement-lock, exploration, autonomous,
and route. Added tests cover blink input leakage, synchronous confirmation,
temporary cloud barriers versus isolated clouds.

Final session state: test1/test2 post-death; test3 contains the saved controlled
CodexRoute6 diagnostic (after CodexRoute9 completed). No game is still running
autonomously. The original non-test session was untouched.
