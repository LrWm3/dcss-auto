# Route-controller live test

Character: CodexAutoCrawl32, MiBe, seed 12129758890624067962.
Session: reused `codex-autocrawl:0` throughout.

Observed progression: D:1–11 → Lair:1–5 → D:12 → Orc:1–2.
The character died on Orc:2 to an orc knight, XL14, turn 19400.
The morgue confirms Orc:1 entry at turn 18586 and Orc:2 entry at 19247.

Morgue: `crawl-0.35/crawl-ref/source/morgue/morgue-CodexAutoCrawl32-20260907-205534.txt`
(relative to workspace root).

This was an iterative development test with save/reloads, not an uninterrupted
validation of the final RC from turn one. Issues corrected during the test:

- Transparent runed-door exploration oscillation: optional runed vaults now
  receive small exclusions and incomplete exploration stays labelled partial.
- Interlevel travel without a known local path: bounded local-exploration
  fallback, with real waiting turns when fog obscures the exits.
- Blink cancellation, barbed-spikes movement, and artefact unwield prompts:
  explicit answers prevent unattended confirmation menus.

Route progress survived the character save/reloads. All four suites passed:
movement-lock, exploration, autonomous, route.

Later route stages (D:13–15, S-branches/runes, Elf, Vaults, Depths and Zot)
were not reached in this live run. Route tests exercise alternative branch
selection, rune possession gates, stage transitions and persistence with
mocked game APIs; they do not establish full-route survival or live rune pickup.

The session is left at the post-death inventory screen. The route configuration
and hook documentation are in `.webtiles/ROUTE.md`.
