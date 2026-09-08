# Six-run autonomous validation — 2026-09-07

Tested the unchanged `.webtiles/rcs/codex-autocrawl.rc` in the same
`codex-autocrawl:0` tmux pane, restarting it sequentially for six fresh MiBe
characters. RC SHA-256 before and after:
`bfc51dd4757afc7a7c41ffa9820098e6d16b33084d9e1e555b2b81a2d9a3b885`.

No gameplay input was sent after character creation until each trial ended
or was classified as incomplete. Incomplete characters were saved, not killed.
Screens were sampled every five seconds. An unchanged screen for 30 seconds
or a four-minute wall-clock limit ended an incomplete trial. Therefore a
timeout is not mathematical proof that a run could never finish.

| Trial | Character | Seed | Result | XL | Turns |
| --- | --- | --- | --- | --- | --- |
| 1 | CodexAutoCrawl26 | 9574034344952554059 | Died D9, wyvern | 10 | 7059 |
| 2 | CodexAutoCrawl27 | 814842380055164672 | Died D9, wight with freezing spear | 10 | 7124 |
| 3 | CodexAutoCrawl28 | 18304311761763738908 | Incomplete: repeated D2/D3 stair cycle; stopped at four-minute limit | 3 | 8954 |
| 4 | CodexAutoCrawl29 | 4795802297515031163 | Died D7, electric eel | 8 | 6008 |
| 5 | CodexAutoCrawl30 | 12129758890624067962 | Incomplete: silenced scroll-reading loop on D2 | 3 | 892 |
| 6 | CodexAutoCrawl31 | 5938935167533909222 | Died D6, gnoll with spear | 9 | 5704 |

Result: **4/6 reached autonomous death; 0 reached D15; 0 cleared D15;
2/6 failed to finish autonomously within the observation limits.**

## Failure evidence

Trial 3 repeatedly printed `Done exploring.`,
`[MiBe bot] floor clear: stair-dipping before committing deeper.`, and
up/down staircase messages. Across samples from 30 to 240 seconds it stayed
at XL3, 46% experience, cycling between D2 and D3 while game time advanced.
Saved on D2. This indicates a repeating stair/exploration cycle rather than
a frozen more-message prompt. The precise root cause was not diagnosed in
this verification-only batch.

Trial 5 repeatedly printed `You cannot read scrolls while silenced!` and
`There is a stone staircase leading up here.`, followed by
`Infinite lua loop detected, aborting.` The unchanged screen was observed for
30 seconds before saving. This is a missing scroll-reading eligibility guard.

## Evidence and recovery

All paths below are relative to `crawl-0.35/crawl-ref/source/`:

- `morgue/morgue-CodexAutoCrawl26-20260907-201223.txt`
- `morgue/morgue-CodexAutoCrawl27-20260907-201315.txt`
- `morgue/CodexAutoCrawl28.txt`; live save `saves/CodexAutoCrawl28.cs`
- `morgue/morgue-CodexAutoCrawl29-20260907-201814.txt`
- `morgue/CodexAutoCrawl30.txt`; live save `saves/CodexAutoCrawl30.cs`
- `morgue/morgue-CodexAutoCrawl31-20260907-201940.txt`

The session was left on trial 6's post-death inventory screen. No RC fixes
were applied during this batch, and no automatic seventh run was started.
