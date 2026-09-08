# Seed 4: tracing from first D:6 entry

Diagnostic only; no tactical policy changes or manually selected combat moves.
CodexD6Entry1 remains paused in codex-bench4 at turn5973, D:6,46/71HP,
on first steam dragon contact in this replay. This is not a benchmark result.

## Observed sequence

| Turn | Action and result |
| --- | --- |
| 3550 | First D:6 arrival,56/56HP, recovering from D:4 shaft to D:7. |
| 3561–3650 | Route-recovery movements encounter gnolls/jelly; combat, then eventual ascent. |
| 5672 | Returns to D:6 at70/70HP after shallower-floor play. |
| 5687–5835 | White imp, then gnoll/orc/bouda fight; recovers before further native exploration. |
| 5836 | Full71HP, native autoexplore. |
| 5897–5898 | Exploration discovers one ordinary orc six tiles north and stops. Tab moves north, exposing an orc warrior. |
| 5899 | Tab moves northwest, exposing an orc wizard. |
| 5900–5901 | Trog's Hand, then another Tab move north exposes the priest. One ordinary-orc contact has grown into a four-enemy pack. |
| 5906–5924 | Wizard turns invisible; warrior dies5907, unseen magic-user kill5922, ordinary orc5924. Intermittent retreats and renewed pursuit. |
| 5934–5935 | Rejected-Tab fallback movement exposes electric eel at full HP. |
| 5937 | Sixth retreat step consumed; disengage state does not prevent subsequent pursuit. |
| 5945–5949 | Eel killed at23HP, priest killed5948;25HP at5949. |
| 5950–5951 | Stale wizard memory expires; waits. Marrowcuda enters view at25HP. No new exploration command was needed for this reinforcement. |
| 5951–5952 | Tab pursuit reveals an unreachable black bear. |
| 5957–5958 | First marrowcuda killed;32/71HP, encounter still disengage, retreats6. |
| 5958–5962 | Isolated-black-bear branch takes FIVE custom exploration steps, not recovery actions. Reveals another marrowcuda. |
| 5963–5968 | Pursues and kills second marrowcuda;44/71HP. Takes another custom exploration step. |
| 5969–5973 | Waits; steam dragon enters view at46/71HP, seven tiles away. Diagnostic pauses before responding. |

## Diagnosis

Native `o` did stop at first hostile contact. The pack expanded mostly through
combat pursuit, then further enemies arrived before recovery. There was no
new native autoexplore between the ordinary-orc contact and dragon arrival.

There is also a direct custom-exploration defect: an unreachable enemy invokes
`isolated_enemy_action` -> `explore_frontier` without a recovery/encounter-intent
gate. At32HP it explored despite `phase=disengage`, exposing another fight.

Source paths explain why this is possible:

- `positioning_action` requires at least three visible enemies and seeks a
  strictly narrower neighboring tile. It is not a persistent lure-back policy
  for the first contact, nor a rule against revealing new terrain during combat.
- `manage_encounter` limits retreat to six steps. If it cannot act, control
  falls through; disengage is not a prohibition on later pursuit/exploration.
- `rejected_autofight_action` paths toward enemies without checking intent.
- `isolated_enemy_action` paths toward exploration without checking HP/intent.

Suggested next design, NOT implemented here: retain a safe approach/retreat
anchor, prefer pulling first contacts into explored ground, and give encounter
intent authority over both native Tab pursuit and custom movement. Reaching a
retreat budget must trigger an explicit hold/fight/escape choice, not silently
resume approach. Separate unreachable-monster handling from permission to
explore while injured.

## Evidence limits and provenance

This replay diverged from the earlier exact steam/priest death at5913. It does
NOT prove that the original wizard, dragon, marrowcuda and priest arrived in
this order. It directly demonstrates encounter-acquisition defects on the same
seed, with the same tactical policy. In this run the wizard and priest were
dead before the steam dragon appeared.

Tracing pauses at first D:6 arrival and at new visible roster contacts; bounded
ready-decision batches and individual actions were authorized through the Lua
console. No manual tactical commands were selected. Native exploration can
contain multiple movement turns within one ready callback; it is not a
per-tile trace of native travel. Diagnostic console timing may interrupt
travel; the reason for replay divergence has not been isolated.

The initial diagnostic snapshot errored at3550 because RC Lua lacks
`you.x_pos/y_pos`. No tactical action occurred at that breakpoint. The live
console supplied functions returning `unavailable`; canonical diagnostics now
guard absent functions. Coordinates are therefore relative monster positions,
not absolute player coordinates. This was a diagnostic repair, not a tactical
intervention, and the run must not be reported as error-free autonomous play.

Full notes: `d6-entry-debug-v1-CodexD6Entry1.txt`.
SHA256: b9b0f1bec2d3ac92b210012e34802527da77880344da4029801016f8389b8e79.
Launch commit:1ebce4c6bd8ea217c401cbeb1688d6c3af697a12.
Launch RC SHA256:6d4bab18e2608cb2f238321c2bfa78d465b9de267fbd5cd81bc9df5afc193b95.
Engine SHA256:54cdf44895903fa3c7ac51278afff390d1bffe6f1abd581dc3529aa47a3d3b38.
Seed:17908030050512890810.
