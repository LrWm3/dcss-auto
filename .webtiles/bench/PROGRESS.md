# Progress journal

## 2026-09-07: establish worst-seed objective

Historical original: ranks `[4, 7, 7, 6, 11]`, minimum **4**.
Historical resilience-v2: `[13, 2, 7, 11, 10]`, minimum **2**.
The latter is a regression, despite its best seed reaching Lair:2.
Historical code snapshots are unavailable; hashes are recorded only when known.

Checkpoint `5b7b6c5` preserves the current bot and regression suites.
Unrelated workspace files are deliberately not staged.

Next candidate: `threat-berserk-v1`. Restore the original adjacent yellow/red
berserk trigger, removing crowd-only activation and the HP floor. Keep emergency
resource use and the stat-zero gear guard. Hypothesis: crowd-triggered rage can
expire before later threats, harming the weakest early-game seed. This is a
testable hypothesis, not an established causal diagnosis. Evaluate all five seeds
without intervention; judge the minimum first. Results go into runs.jsonl.

### threat-berserk-v1 result (commit d1fbbc3)

Reached ranks `[2, 10, 21, 6, 9]`, minimum **2**. Four deaths and one
movement-loop pause (CodexBench4 saved on D:6 after clock advanced from 6838.7
to over 10664 with unchanged XL8 97% and repeated shallow-water/priest messages).
The former weakest seed improved D:2 -> D:10, but seed 6144198052690956201
fell from Lair:2 -> D:2. **Rejected: no minimum improvement.**

The rank21 run visited D:14 (including a shaft) before returning to Lair and
dying on Lair:5. This illustrates why `reached` is not `cleared`: maxima can
include involuntary travel. Do not present that run as a D:14 clear.

Restored the offensive policy to checkpoint 5b7b6c5 after recording the rejected
candidate. Its exact tested variant remains reproducible at d1fbbc3. This is a
rollback to the working checkpoint, not promotion of the resilience variant:
the historical original still has the best observed minimum (4 versus 2).

Next target: early gnoll/Robin encounter positioning on the two weakest seeds,
plus the reproducible D:6 priest movement loop. Require a full fixed-seed batch
and a higher minimum before claiming an improvement. No runs remain active.

## Policy clarification and structural cleanup

Per user guidance, a worse/tied minimum does not require rejecting an idea or
restoring code. The historical decisions above remain recorded, but subsequent
iterations can retain promising work and address its weaknesses. Keep the
worst-seed metric as the primary outcome, separate from development decisions.

This revision is a behavior-preserving refactor, not a new survival experiment:
tactical thresholds centralized in AUTOCrawl_TACTICS; guarded input and turn
completion checks shared; combat decomposed into rejected-autofight recovery,
isolated-enemy handling, and berserk selection. The previous defaults remain.
It does not fix the known priest movement loop or claim higher progression.

Verification: five Lua regression suites plus policy-trace comparisons against
the previous checkpoint. No live seed run is represented by these mocked checks;
therefore no new progression rows are added to runs.jsonl for this refactor.

## positioning-v1 experiment

Add bounded pre-melee positioning for visible groups: choose a safe known tile
with fewer approaches without moving closer to enemies; do not retreat from
adjacent attackers. At a known choke, wait at most three times for non-casters,
stopping on damage. Limit repositioning to six moves per continuous encounter.
Unknown terrain cannot count as a wall. This is a positioning heuristic, not
complete ranged-threat or opportunity-attack reasoning. Six regression suites
pass before the fixed five-seed trial. Keep the policy configurable.

Result: reached ranks `[5, 2, 5, 6, 5]`, minimum **2**. All five died naturally;
no observed stalls or intervention. The third character died on D:3 after
previously reaching D:5. The early Robin seed remains the bottleneck. This is not
a measured improvement; retain the configurable candidate for further iteration.

## Config-driven runner

Added batch.py and a five-seed JSON config to snapshot RC revisions, launch
parallel tmux games, monitor without gameplay input, and import verified deaths
idempotently. Suspected stalls and reported completions stay distinct from
verified terminal results. This tooling change does not alter the bot policy.

## Tactical variants: threat-position, early-support, emergency-rage

Tested three five-seed batches with immutable, hashed RC snapshots. All 15
characters died autonomously; no observed stalls and no gameplay intervention.
The runner collected each death, and reused the five support sessions for the
emergency-rage batch. A runner safeguard initially refused the postmortem
inventory screen; fixed it to validate the process identity, matching death dump,
and absence of a save before reuse. No live game was interrupted.

| Variant | Reached ranks in fixed seed order | Minimum | Deltas vs positioning-v1 |
| --- | --- | --- | --- |
| positioning-v1 reference | 5, 2, 5, 6, 5 | 2 | — |
| threat-position-v1 | 2, 13, 7, 8, 8 | 2 | -3, +11, +2, +2, +3 |
| early-support-v1 | 5, 2, 5, 6, 5 | 2 | 0, 0, 0, 0, 0 |
| emergency-rage-v1 | 5, 2, 5, 6, 5 | 2 | 0, 0, 0, 0, 0 |

Threat-position disables crowd-triggered berserk and removes its HP floor while
keeping positioning. Rank13 is Lair:2. Earlier support raises healing, escape,
haste, might, and ally thresholds; emergency-rage changes only berserk_hp to zero.
Exact overrides are tracked in the named JSON configs. These reached milestones
do not establish floor clears. Every minimum still trails historical-original's 4.

The Robin seed dies at exactly turn532 under positioning, early support, and
emergency rage, but reaches Lair:2 under threat-position. This suggests the crowd
trigger/timing is more consequential here than the HP cutoff or resource
thresholds. Conversely threat-position's first seed dies to D:2 gnolls while
berserk. These are single-replay observations, not proof of a causal mechanism.
Next useful target is encounter-specific crowd timing/positioning, not simply
raising more consumable thresholds. Main RC remains unchanged; retain all three
variants for further iteration without claiming a measured improvement.

## Encounter controller v1

Added a persistent encounter layer (prepare/fight/disengage/recover/idle) above
single-action helpers. Tracks recent unseen danger, HP loss, group peak and
bounded retreat budget. Emergency resources now precede movement restrictions
and remain eligible during recent unseen attacks. Recovery holds exploration;
crowd berserk requires multiple adjacent foes in a bounded visible group.
This is a first-stage controller, not a full cover or escape-path planner.

Fresh five-seed batch at 229d77f: reached `[D:10,D:2,D:7,D:8,D:9]`, minimum2,
four deaths and one paused game. Deltas versus positioning-v1: `[+5,0,+2,+2,+4]`.
No overall minimum improvement; seed2 died at XL2 to Natasha before Robin.
Seed1 killed Sigmund and later died to Harold. The trace does not isolate which
policy change caused that improvement. No reached floor is claimed cleared.

CodexEncounter3 paused at turn6483 on D:7 after retreating while mesmerised by
Maggie. Captured dump, saved character, and backed up save under the batch folder.
Added mesmerism guard at 3fd66be and resumed the saved game in the same tmux
session. It advanced to turn6500 and died to an orc warrior without another
movement pause. Recorded separately as encounter-v1-mesmerism-resume: this is
a **mixed-policy saved-state diagnostic**, not a fresh seed replay or replacement
for the paused benchmark row. The current fixed RC has not had a full fresh batch.

Seven Lua suites and nine runner tests pass. Keep encounter controller enabled
for iteration. Known next issue: the resumed morgue repeatedly shows `survival:
fear`, a targeting prompt, and `Unknown command` before ordinary melee. The
generic guarded consumable helper cancels this targeting interaction; strategic
escape intent is therefore not reliably executed. Also still missing: full
ranged-cover planning and an effective resource-less escape from adjacent foes.

## Fear fix and D:2-focused experiments

Fixed known fear's area-preview confirmation (`r<slot>f` before Escape guards),
verified against local item-use.cc and a regression test. Reran the five fresh
seeds as encounter-v2: `[11,2,10,8,10]`, all deaths, minimum2, no observed stalls.
The prior mesmerism seed now reaches D:10 autonomously. This batch's terminal
message windows do not retain a fear activation, so source/unit coverage should
not be described as an isolated live fear-confirmation test.

Tested early_commit (XL<=4): permit berserk against adjacent dangerous/multiple
foes despite disengage intent, and suppress preparatory repositioning for known
casters. Result `[4,2,2,6,5]`, all deaths, minimum2. The Robin seed killed Natasha
and Robin but died to adder poison at turn710; another seed regressed to D:2.
Retained the configurable code but disabled it in the working default.

Next tested `explore_stop=shop,greedy_pickup_smart` to return control after new
useful pickups for equipment preparation, on the encounter-v2 tactics. Result
`[5,7,3,6,5]`, all deaths, minimum3. Deltas versus encounter-v2 are
`[-6,+5,-7,-2,-5]`: improved worst-seed metric, substantial individual regressions.
The former D:2 seed wore its evasion ring and reached D:7. This does not isolate
equipment from timing/trajectory changes, but it supports continuing preparation
work instead of simply increasing berserk frequency.

Inspection of remaining cooldown messages found a real API mismatch:
`you.exhausted()` checks DUR_EXHAUSTED, while berserk eligibility also checks
DUR_BERSERK_COOLDOWN. Added shared recovery check for `on berserk cooldown` to
encounter transitions, activation gates, and pre-exploration recovery. Tested as
pickup-recovery-v1 with the same five seeds, exact revision 8491831.

Final pickup-recovery-v1 result: `[Lair:5,D:11,D:3,D:6,D:8]`, ranks
`[16,11,3,6,8]`, all deaths, no observed stalls, minimum3. Versus encounter-v2:
rank deltas `[+5,+9,-7,-2,-2]`; versus pickup-prep: `[+11,+4,0,0,+3]`.
The old D:2 bottleneck reaches D:11; new bottleneck is seed1760771545328102746,
dying to invisible Sigmund's +4 venom scythe on D:3 while poisoned and recovering
from berserk. Seed1 dies to a Lair:5 catoblepas. This remains below historical
original's minimum4 and is one screening replay per seed, not a robust promotion.

Twenty fresh games across four batches completed autonomously this turn. All
snapshots, commits, hashes and death evidence recorded. Seven Lua suites and nine
runner tests pass. Current working RC retains pickup stops and true berserk
cooldown recovery; early_commit is disabled but available for further iteration.
Remaining tactical limitations include ranged-cover planning, resource-less
disengagement from melee, and commitment under unseen poison/confusion pressure.

## Targeted Sigmund scenario (seed 1760771545328102746)

Only this seed replayed. Baseline pickup-recovery-v1 dies on D:3, turn2517, to
Sigmund's +4 venom scythe. Added bounded caster memory, proactive protection,
bounded blind probes, and marked-disturbance pursuit. Iteration results:

| Version | Terminal result | Turns | Finding |
| --- | --- | --- | --- |
| sigmund-memory-v1 | D:3 death | 2472 | Retreat while slowed remains inside scythe reach |
| sigmund-memory-v2 | D:3 death | 2492 | Committed against Natasha before Sigmund appeared; spent four Hands |
| sigmund-memory-v3 | D:3 death | 2398 | Avoided early caster berserk; ordinary melee/retreat still loses |
| sigmund-memory-v4 | D:3 paused | 2396 | Lua gsub returned replacement count as second command; saved game |
| sigmund-memory-v5 | D:3 death | 2399 | Fixed command format; conservative commitment still too late |
| sigmund-memory-v6 | D:7 death | 6631 | Killed Sigmund at turn2389, continued, died to centaur |

V4 metadata entry corrected before committing: replaced an erroneous placeholder
hash with the immutable tested.rc digest and filled exact commit/engine hashes.
The game remains saved as CodexSigmund4; no pause is relabelled as a death.
Most replays reused codex-bench3; after saving the paused character, subsequent
trials reused the already-existing codex-bench4, leaving the saved game untouched.

Successful v6 closes the gap to the visible priority caster before ordinary
retreat, prioritizes its adjacent attack, and permits direct berserk at HP>=40%
with at most four visible enemies. Missing caster still vetoes commitment.
Preemptive Hand budget is capped at two per floor; generic emergency Hand remains.
These are tactical heuristics, not evidence that all invisible casters are solved.
No full five-seed comparison was run; results cannot raise the benchmark minimum.

Unchanged-RC repeat sigmund-memory-v6-repeat also killed Sigmund at turn2389 and
died on D:7 at turn6631. Both snapshots hash to
0d8f8d8dbcde5f528494798ca9b10f0250b2ea4068ba079598b07a8e6414b8b0.
Thus 2/2 final-policy replays pass this encounter; deterministic agreement on
one seed is not broad statistical validation. Seven Lua suites and nine runner
tests pass. Current RC retains v6; six completed deaths and one saved pause are
recorded across this targeted iteration series, with no games left running.

## Full-batch regression check of Sigmund policy

Ran unchanged final targeted RC (SHA256
0d8f8d8dbcde5f528494798ca9b10f0250b2ea4068ba079598b07a8e6414b8b0)
as sigmund-full-v1. Five fresh fixed-seed games, all autonomous deaths, no
observed stalls or gameplay intervention. Reused finished sessions; left the
saved CodexSigmund4 diagnostic untouched. No bot code changed for this check.

| Fixed seed order | Prior pickup-recovery-v1 | sigmund-full-v1 | Rank delta |
| --- | --- | --- | --- |
| 1 | Lair:5 (16) | D:10 (10) | -6 |
| 2 | D:11 (11) | D:14 (21) | +10 |
| 3 | D:3 (3) | D:7 (7) | +4 |
| 4 | D:6 (6) | D:6 (6) | 0 |
| 5 | D:8 (8) | D:9 (9) | +1 |

Minimum reached rank improves **3 -> 6**, above historical-original's 4.
One clear per-seed regression: seed1 died to a D:10 boulder beetle instead of
reaching Lair:5. Seed4 remains an electric-eel death on D:6, now the bottleneck.
The targeted seed again killed Sigmund at turn2389 and died on D:7 (turn6628,
slightly different from the two earlier turn6631 deaths).

Important: seed2 reached D:14 by a three-floor shaft from D:11 at turn9637,
then died to a centaur. Its rank increase is not evidence of route completion
or D:12–14 clearing. Cleared telemetry remains unknown for every run. This is
the best observed full-batch minimum so far, but only one screening batch on
this policy; a replicated full batch is needed before claiming robust improvement.
RC retained unchanged; five result rows and morgue evidence committed.

## D14 shaft / off-route recovery

The D11 -> D14 shaft exposed a priority inversion: the route controller attempted
return travel only after encounters, equipment, and other ordinary actions, with
native exploration as a failed-travel fallback. Added persistent target/position
and recovery state. Below an unfinished same-branch target, prioritize upstairs
and one-turn discovery of upstairs, without descending or advancing route stages.
Explicit shafts during interbranch travel return to the departure depth. Loaded
off-target characters and airborne shaft messages are covered too. Emergency
survival, immobility/confusion, unseen threats, and adjacent combat retain their
gates; heal safely between encounters before further discovery. No safe exit or
frontier produces an explicit pause, not fabricated floor completion.

Eight Lua suites and nine runner tests pass. New mocked tests cover D14 -> D13 ->
D12 -> D11, unchanged target/clear state, adjacent versus distant monsters,
unknown upstairs discovery without descent, safe healing, blocked exits, save/
load, loading already below target, and legitimate planned/interbranch travel.
These establish controller behavior, not live survival through D14.

Reused codex-bench2 for three natural replays of seed 13772526223844354029:
shaft-recovery-v1/CodexShaft1 (ac15585), v2/CodexShaft2 (e56b322), and
v3/CodexShaft3 (447facc). All died on D10 to Lodul's ogre at turn8064, XL10.
No observed stalls or gameplay intervention. None reached the prior D11 shaft,
so live shaft recovery remains UNVERIFIED. This is a lower reached result than
the earlier D14 run, but these deaths occurred before exercising the intended
recovery; the reason for the changed pre-shaft trajectory is not established.
Do not claim a benchmark improvement or successful D14 ascent from these runs.
Final RC SHA256:
b414e3f917b571cc88f71a9649b80c3c11e0076f1febe9337841f1048995f364.
All three death rows and immutable evidence retained. No test games left running.

## Lodul diagnostic breakpoint and wand evaluation

Added opt-in `AUTOCrawl_TACTICS.debug_encounters` (default false), configurable
`AUTOCrawl_DEBUG_NAMES`, a first-sighting breakpoint before combat, and persisted
debug pause/seen state. `autocrawl_debug_report()` reports visible-monster wand
success probabilities and available consumables; `autocrawl_debug_resume()`
explicitly resumes without immediately breaking on the same unique again.

lodul-debug-v1 reuses codex-bench2 with CodexLodulDebug1 and seed
13772526223844354029. Successfully paused at Lodul, D10 turn8128, HP91/91.
Recorded as an intentional diagnostic pause, not a stall or completed trial.
The inventory and corrected read-only inspection are in evidence/lodul-debug-v1-*.
Charm succeeds 62% against the three visible ogres, 44% against Lodul; mindburst
81% / 67%, damage3d13. Warping damage3d10, preview blink chance67%; nearer ogres
intercept the attempted shot toward the pack centre. Cancelled preview spent no
turn or charge. A front-ogre charm is the recommended experimental opening,
followed by reassessment; automatic wand execution is not enabled yet.

Fixed diagnostic spell-name lookup from "Charming" to the engine's "Charm" and
added a regression test. Live snapshot remains immutable; corrected chances were
queried directly without gameplay action. Nine Lua suites and nine runner tests
pass. Character is still alive and paused in codex-bench2 for the next experiment;
do not reset it. No survival improvement claimed from this diagnostic run.

## Generic combat wands: live Lodul intervention

Implemented generic charm/finisher/safe-blast scoring, with conservative targeting,
minimum success thresholds, friendly-fire vetoes, and attempt budgets. Ten Lua
suites and nine runner tests pass. No unique-specific combat exception.

Tested on the already-paused CodexLodulDebug1. Initial item-slot API mismatch and
same-filename reload caching were resolved without spending game turns. Corrected
snapshot 780ebd2 used two charm and two mindburst charges successfully, no warping.
Lodul died at turn8143. After 51 total turns from the breakpoint, the character
was alive at turn8179, HP91/97, XL11, no visible hostiles, deliberately paused.
This is a successful local encounter test, not proof of improvement over the old
policy on exactly the same state and not a from-start autonomous benchmark.

Preserved separate machine-readable episode metadata in interventions/lodul-wands-v1.json,
end dump and observed action history in evidence/lodul-wands-intervention-v1-*.
Do not reset codex-bench2: it remains paused with the new wand policy installed.
The original diagnostic pause row is unchanged. Broader regression/replay remains
to be tested; warping was evaluated but not fired in this encounter.

## Full seed replay with combat wands

wands-seed2-v1 / CodexWandsSeed2 ran from D1 to natural death on fixed seed
13772526223844354029, without intervention, debug breaks, or observed stalls.
Reused finished codex-bench1; preserved the paused CodexLodulDebug1 in bench2.
RC SHA131a44108b040c19ef34a1edbd31f0efdc0d6b0529a675dabc383f0d5d20907d,
launch commit00436a6, unchanged wand policy from the successful local intervention.

Killed Lodul at turn7590 (encountered7579), survived D10, died D11 turn10257,
XL11, to an ogre mage's 40-damage bolt of magma. No shaft recorded. At death:
-23/101HP, slowed/on berserk cooldown, mighty, regenerating with Trog's Hand.
The last messages show killing an arcanist, closing to the ogre mage, taking
a heavy magma hit, refreshing Hand, and being killed by the next magma bolt.

All offensive charges were spent: charming13, mindburst15, warping10. Nine
warping charges were already spent in the XL7–9 band. Thus all three wand
execution paths worked in a natural run, but reserve management is an open
problem: only digging remained for the final encounter. Available resistance,
lignification, fog, and unidentified escapes were still unused at death.
No claim that conserving charges alone would have prevented this death.

Reached rank11 versus rank10 in the three pre-wand shaft-recovery trials. The
older sigmund-full-v1 D14 result was shaft-inflated and is not a D14 clear.
This is a single-seed screening result, not an improved five-seed minimum or
a replicated survival claim. Kept the RC unchanged and imported death row /
immutable morgue evidence via the runner. New run finished; original diagnostic
character remains alive and paused in codex-bench2.

## HP/threat gating plus four-cast encounter cap

Implemented user rule exactly: HP score floor(10*HP/maxHP), clamped0..10;
visible hostile threat3=6, threat2=1, others0; strict HPscore<threatscore permits
consideration by the existing wand selection policy. Four spent casts maximum
per encounter, with no emergency override. Count persists across LOS gaps,
floor changes and save/load; reset after encounter memory ends and full recovery.
Fourth cast writes a permanent cap note with the observed enemy roster; later
roster additions update the note without repeated same-roster spam.

Ten Lua suites and nine runner tests pass, including HP boundaries, strict
inequality, red weighting, successful-versus-rejected casts, hard cap beyond20
turns, note contents, persistence and encounter reset. Policy documented in
WAND-POLICY.md.

wand-gate-seed2-v1 / CodexWandGate1 reused finished codex-bench1 with fixed seed
13772526223844354029. No gameplay intervention. Killed Lodul8056 and the D11
ogre mage10202, progressed through Lair/Orc/deeper Dungeon, and reached Shoals:2.
Paused turn24759, XL15, HP137/137, on the existing mesmerisation/movement-rejection
guard. Preserved the character there; did not fix or manually advance this trial.
Read-only post-pause console confirmed ROUTE_STATE.done["D:15"]=="clear", stage6.
Original CodexLodulDebug1 remains separately preserved in bench2.

Used10 offensive casts (charm3/mindburst5/warping2), versus38 in wands-seed2-v1
which died D11. Remaining16/17/20 respectively, including additional pickups.
One D15 encounter hit the cap: note22341 and an updated roster note22421, both
encounter22304. Roster includes centaur warrior, cyclops, ugly things, yaktaurs,
slime creatures and other enemies; full counts in evidence. It survived a6HP
low point without bypassing the cap. See accompanying observations for details.

Recorded as paused/reached rank24, not a death or full route win. This is a
promising one-seed result, not a five-seed minimum or replicated causal claim.
Retained RC6638c14ee184c4a078de1e6363ee56fbe92ec418009b195d0ec0d3a5291bc158
(tested commit96bdfd6). Immutable dump, pause row and observation notes committed.

## Mesmerisation movement fix — isolated live intervention

User priority: fix movement before further tactical changes. Commit34e11d3;
RC f17f73a940e6847394827d922ad910b0aaa10c6ec7dbdd117fbb36e4b87d977d.
The generic "cannot move" latch also caught "cannot move away from" and
prevented all subsequent combat. Classify directional rejections separately;
unknown restrictions retain their safe pause. Recover pre-fix unclassified
latches on mesmerised hotloads. Use engine view.withheld on actual first steps
(not hypothetical BFS nodes), direct adjacent attacks, and one-step pursuit to
melee range. Wait a real turn if no legal path exists or a direction was rejected.
This prevents native autofight/explore from repeatedly choosing illegal pursuit.
Survival, wand gate/cap, confusion and true immobility policies remain intact.

Ten Lua suites (including new mesmerisation cases) and nine runner tests pass.
Cases cover forbidden first steps with legal alternatives, all directions
withheld, old-latch recovery, directional retry backoff, unknown rejection
while mesmerised, adjacent attacks, confusion, tree form, and effect ending.

Hotloaded into existing codex-bench1 / CodexWandGate1 at24759, HP137/137,
without a manual gameplay action or latch reset. Diagnostic stop set for24789.
The character advanced, moved off the stairs and killed the Shoals:2 avatar;
vanquished avatar count increased from1 to2. Died naturally at24779, -11/137,
to a17-damage satyr arrow, with four sirens and a satyr visible and mesmerisation
still active. No DLua errors. Movement deadlock resolved in this live encounter;
surviving ranged Shoals packs is not solved or claimed by this narrow fix.
Separate interventions/mesmerism-v1.json and immutable endpoint evidence preserve
this mixed-version result; original paused seed row remains unchanged. Bench2's
Lodul diagnostic character was untouched.

## Full five-seed rebenchmark: wand-mesmerism-full-v1

Fresh parallel games, no tactical overrides, tested commit
cb56138ac4a2986182d13f547b169f9144bb0186 and RC
f17f73a940e6847394827d922ad910b0aaa10c6ec7dbdd117fbb36e4b87d977d.
Engine54cdf44895903fa3c7ac51278afff390d1bffe6f1abd581dc3529aa47a3d3b38.
Reused verified finished runner sessions support1/support2/bench5/bench4/support5;
preserved diagnostic characters. All five naturally died without gameplay
intervention; no RC edits during the batch. Exact config, rows and morgues saved.

Comparison with the last complete five-seed batch, sigmund-full-v1:

| Seed index | Previous reached | New reached | Death location / cause | Turns | XL |
| --- | --- | --- | --- | --- | --- |
| 1 | D:10 | D:10 | D:10, boulder beetle | 9168 | 10 |
| 2 | D:14 | D:12 (after Lair) | D:12, Frances's summoned sun demon | 17934 | 14 |
| 3 | D:7 | D:7 | D:7, wyvern | 6631 | 9 |
| 4 | D:6 | D:7 | D:6, orc priest's divine providence | 5913 | 8 |
| 5 | D:9 | D:10 | D:10, electric eel | 9152 | 11 |

Reached ranks change [10,21,7,6,9] -> [10,17,7,7,10], paired deltas
[0,-4,0,+1,+1]. Recorded minimum rises6->7, but seed4's apparent gain is
a D:4-to-D:7 shaft at3374, not a confirmed D:6 clear; it still dies on D:6.
Do not treat this as established improvement in weakest-seed survival.
Likewise previous seed2 D:14 was shaft-inflated; numeric reached regression
does not fully describe its longer new run with Lair progression. This replay
also falls short of the isolated wand-gate-seed2-v1 run reaching Shoals:2.
No new D:15 clear demonstrated. One replay per seed is a screening result,
not causal isolation of mesmerisation versus wand changes or random divergence.

Seed2 retained charm12/mindburst16/warping10 charges and used heal wounds during
the fatal Frances pack, while slowed on berserk cooldown. Resource exhaustion
is therefore not sufficient to explain that death. No automatic policy changes
made during this benchmarking request; all original baseline rows remain intact.

## Steam dragon / priest death: single-decision diagnostic replay

steam-debug-v1 / CodexSteamDebug1 replayed seed4 with a D:6 dragon breakpoint
at5877,58/71HP. Inspected44 ready decisions individually through the exact
original death at5913,-9/71HP, priest smite13, score1498. Seven rejected Tabs
spent no turn; fatal action explains the apparent extra difference in counters.
No manual tactical actions, policy changes or actual Confusion status.

Key discovery: after killing dragon/marrowcuda the character successfully
retreated out of priest LOS at5894. Stale unseen-wizard memory then caused
blind probes and an upstairs path, re-exposing the priest and consuming all
six retreat steps. Rejected-Tab fallback pursued through water despite the
encounter remaining in disengage. Wizard memory finally expired5909, after
the eel was exposed. Unseen attacks really occurred before steam; collateral
wizard death at5881 is strongly suggested by autopickup/experience messages
and two wizard kills attributed to others. Exact identity remains inference.

Full44-decision table, evidence limits, logging setup and findings are in
evidence/steam-debug-v1-analysis.md; full notes in the immutable morgue.
Separate interventions/steam-debug-v1.json records this diagnosis, not an
autonomous benchmark row. Batch manifest locally marked verified death to
permit safe future reuse. Added opt-in diagnostics (default off) and helper;
all10 Lua regression suites passed before replay. No tactical fix yet.

## D:6 entry trace: encounter acquisition and premature exploration

d6-entry-debug-v1 follows seed4 from first D6 arrival3550 to steam dragon
contact5973. Paused alive46/71HP in codex-bench4. No tactical changes.
This replay diverged from the exact5913 death; do not conflate their histories.
Native explore stopped at a lone orc; three pursuit moves exposed warrior,
wizard and priest. Subsequent pursuit exposed an eel. At32HP after a marrowcuda
kill, the isolated-black-bear branch explored five steps despite disengage,
exposing a second marrowcuda; the dragon then arrived while waiting at46HP.
Intent does not constrain fallback movement once bounded retreat fails.

Saved full notes, timeline and separate diagnostic metadata in evidence and
interventions; no autonomous result row added. Fixed diagnostic-only optional
coordinate API error at entry with live placeholder functions and a canonical
guard. See evidence/d6-entry-debug-v1-analysis.md for provenance and limitations.

## Isolated-enemy recovery anchors

Added a recovery gate before route recovery/combat exploration. Injured players
with no reachable enemy latch recovery until full HP and berserk recovery is
complete. Reaching the six-step combat retreat cap no longer permits frontier
exploration in this case. Priority: current visit's arrival upstairs, last
recorded recovery-wait position, entry position. Replan one ordinary step per
ready through known safe cells; if a usable anchor is visible, wait instead.
Unusable anchors fall back down the list; absent anchors allow waiting against
isolated melee only. Newly reachable enemies return control to combat.

Bot reserves travel waypoint9 as a stable visit origin (engine delta is player
minus origin). Coordinates survive native travel/teleport but anchors reset on
floor transitions, including revisits; no cross-visit rest history yet. Ordinary
arrival upstairs identifies the arrival-stair anchor; shafts use entry fallback.
Engine monster range includes weapons/spells/wands. Ranged threats seek an
anchor path but pause if none exists rather than blindly healing. Unseen threats
retain dedicated handling and cannot fall through into custom exploration.
No stair traversal or general Tab/luring change was added.

11 Lua suites pass, including new isolated-recovery tests for priority, delta
sign, visible anchors, HP latch, LOS loss, retreat exhaustion, ranged/unseen
threats and floor reset. This is local implementation/unit validation only:
CodexD6Entry1 is still paused on its original RC at5973; no live rerun or
autonomous benchmark result claimed.

## Fresh seed4 anchor retest: new early pause

User authorized wiping the paused diagnostic game. Verified codex-bench4
belonged to CodexD6Entry1, stopped that session, and moved its exact save to
batches/d6-entry-debug-v1/CodexD6Entry1.discarded.cs (recoverable). Prior trace
evidence remains unchanged. Relaunched same session/seed as CodexAnchor1 with
canonical commit2bbc8a3, clean RC snapshot a0c054c09b6f1a9bb9e4ce85eb52fd1c20ebb967c9854f301b4bfe4380e755b4,
diagnostic pauses OFF. No tactical inputs or edits during the trial.

Autonomously paused at3483 on D:7 after shaft, XL6,50/56HP: steam dragon
became unreachable behind steam and the new isolated-recovery ranged safety
branch had no safe anchor path. This is a new regression, not death or progress
success; it did not reach the target D6 black-bear scenario. Recorded outcome
paused in runs.jsonl with immutable dump. Only read-only dump command after
the pause; character remains there for diagnosis. The gate conflates temporary
cloud isolation with the recovery-anchor case and needs an autonomous fallback
for transient barriers/ranged danger. No additional tactical changes in this
retest turn.
