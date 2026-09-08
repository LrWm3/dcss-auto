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

## Steam-dragon-specific charge experiment

User requested aggressive pursuit through steam rather than generic cloud or
unseen-enemy reasoning. Added steam_charge (default on),12-turn last-sighting
memory and8 hidden pursuit steps. Track nearest visible dragon in waypoint9
visit coordinates; follow known terrain toward it, allowing steam damage only.
Other unsafe clouds, exclusions, movement locks and mesmerism remain guarded.
Hidden pursuit requires steam still present, stops at the remembered square,
and expires on time/step limits or floor change. Confirmed named kill clears it.
Visible adjacent dragon receives combat priority; existing survival/wands and
berserk decisions remain available. No general Tab/luring overhaul.

Also corrected a wiring error in the preceding anchor patch: its observer had
landed in a stair-related scanner, not normal ready. It now runs every normal
decision before dragon observation. The prior missing-anchor pause may therefore
also reflect missing initialization, not only the intended ranged safety gate.

Archived CodexAnchor1's save to its batch directory and reused codex-bench4.
Two fresh autonomous trials on seed4, no debug pauses or tactical intervention:

| Version | Commit | Result |
| --- | --- | --- |
| steam-charge-seed4-v1 | 49e32f4 | Death D6 eel5963,XL8; maxD7 via shaft. |
| steam-charge-seed4-v2 | e59dc14 | Same outcome/turn, with adjacent combat priority ahead of route recovery. |

Both note visible steam-dragon charge at3478–3480,56HP, and pass the previous
3483 pause. Neither records remembered-position charge, nor a dragon kill;
do not claim live validation of obscured pursuit or survival improvement.
Both autonomously reach terminal death without a new pause, not a D15 clear.
Exact hashes and immutable morgues are in append-only result rows/evidence.
12 Lua suites and9 runner tests pass. Steam tests cover unsafe steam traversal,
remembered targets, shared-map immutability, other clouds/exclusions, expiry,
step cap, destination arrival and floor mismatch. No five-seed batch yet.

## Simple approach experiments: hold / lure / frontier

Implemented one bounded first-contact helper (numeric approach_mode):
0 unchanged,1 wait up to4 turns,2 retreat up to2 safe nonfrontier floor steps
toward current visit's rest/entry anchor then wait up to4,3 wait only if a
candidate pursuit first step is frontier. Waiting stops upon damage or known
ranged threat; melee contact ends the approach policy for that encounter.
Steam dragon, confusion, mesmerism and movement locks retain priority.
Logs each action, HP and visible enemy count in notes. This is not a full
encounter-isolation guarantee: budgets eventually fall back to normal combat,
and enemy reinforcements can still arrive. No general ranged-kiting policy.

All tested from commit43d2c3e with snapshot overrides on seed4:

| Policy | Character | Outcome |
| --- | --- | --- |
| Previous normal approach | CodexSteamCharge2 | D6 eel death5963,XL8 (maxD7 via shaft). |
| Hold4 | CodexHold1 | D6 priest death5798,XL8. Final view12marrowcudas+priest. |
| Frontier hold4 | CodexFrontier1 | D6 priest death6279,XL8. |
| Lure2+hold4 | CodexLure1 | Reached D11 at91/91HP,XL10, blocked on friendly two-headed-ogre attack prompt. |
| Clean lure repeat | CodexLure2 | Same D11 prompt/fullHP; no intervention, left intact in codex-bench4. |

IMPORTANT correction: after saving CodexLure1's prompt screen, attempted
inspection sent n/C-d then diagnostic Lua text without verifying console entry.
The text was interpreted as gameplay, removed equipment and advanced play;
subsequent boulder-beetle death12473 is contaminated. The automatic collector's
death row is preserved but SUPERSEDED by an appended paused/non-autonomous
correction with pre-intervention screenshot evidence. Never count that death
as autonomous. Clean repeat independently reproduced the same blocked state;
recorded paused using screenshot only, exact turn unknown (displayed12480.1 is
game time, not turn count). No speculative cause assigned to ally attack yet.

Retained mode2 as experimental canonical default; exact RC SHA matches both
lure trial snapshots f5a2db15168247e97af568cddc08f25538ae78494c345baa1ad7feef7d000447.
This improves observed progression of this weak seed but is NOT a completed
autonomous run, a five-seed minimum improvement, or proof of fewer simultaneous
enemies. Follow-up priority is the reproducible allied-attack prompt, then a
full seed batch.13 Lua suites and9 runner tests pass; regression tests cover
bounded waits, damage/ranged bailouts, melee latch, anchor lure and frontier
restriction. Existing diagnostic sessions were not replaced; frontier used
verified finished codex-support1 while lure remained in codex-bench4.

## Ally-protection fix and full five-seed rerun

Source inspection found blind disturbance cycling had no visible-ally guard;
custom BFS movement also allowed non-hostile occupied destinations. Added
safe_probe_command (skip friendly/neutral/unknown-attitude occupants, wait if
all directions protected), protected-occupant exclusion in can_step, and a
fail-closed `Really attack ...` handler that sends n and schedules CMD_WAIT
on next ready. Marked disturbances also reject protected occupants. Never
approve friendly fire. Exact command behind the prior prompt was not captured;
these are demonstrated unsafe paths, not a claim of a recovered stack trace.

14 Lua suites and9 runner tests pass, including all-protected surroundings,
preferred/default probe rejection, hostile allowance, movement protection and
prompt cancellation. Archived exact CodexLure2 save in its prior batch directory
and reused the same session; other diagnostic characters untouched.

Fresh parallel batch lure-ally-full-v1 tested clean commit366caa7, RC SHA
735a90db2b562b171bc17caf906709c5112748a078e8111df8c9cdfddda62d08,
engine54cdf44895903fa3c7ac51278afff390d1bffe6f1abd581dc3529aa47a3d3b38.
No mid-run RC edits or tactical input. Four natural deaths, one route pause.
For paused seed4, opened and VISUALLY VERIFIED Lua console before sending only
crawl.dump_char(), then Escape; no gameplay mutation or input contamination.

| Seed | Last full batch endpoint | New endpoint | Turns / XL |
| --- | --- | --- | --- |
| 1 | D10 boulder beetle death | D11 centaur warrior arrow death | 10287 / 11 |
| 2 | D12 Frances sun demon death after Lair | D15 yaktaur death | 24524 / 15 |
| 3 | D7 wyvern death | D3 Sigmund poison death | 2973 / 6 |
| 4 | D6 priest death (shaft maxD7) | D11 explored, route to Lair1 made no progress, paused99/99HP | 13448 / 11 |
| 5 | D10 eel death | D6 Pikel lemure death after D3 shaft | 2336 / 5 |

No ally-attack lock recurred; seed4 passed the old prompt point and survived
additional fights to finish exploring D11. This supports the targeted fix, not
a guarantee against all prompts. It now has a distinct routing blocker, left
intact for diagnosis. Seed2 entered D15 at24497 and died24524; NOT a D15 clear.
All evidence and five outcome rows saved. Reached ranks [10,17,7,7,10] ->
[11,22,3,11,6], minimum7->3. Seed5's D6 is shaft-inflated. Thus the overall
experimental stack regresses weakest-seed resilience despite deeper survivors;
do not advertise this as benchmark improvement or an all-terminal success.
This comparison includes approach/steam/anchor changes since the prior full
batch, not an isolated estimate of the ally guard's effect. Kept the experiment
for iteration; next weaknesses are seed3 early Sigmund and seed4 Lair routing.

## Seed4 required entrance fix; seed3 Sigmund death review

Read-only console at the paused seed4 position established enter_lair at(8,-4)
was excluded, surrounded by plants and two oklob plants (also listed in dump
annotations). Native G refused this genuinely dangerous exclusion; additional
exploration of the already-complete floor could not change that.

Added required_entrance_action after repeated failed native travel, and before
ordinary approach/recovery once active. It targets only the locally known
required branch entrance, replans one movement step each ready and permits
travel-excluded terrain without deleting exclusions. Clouds/traps/runed doors,
protected occupants and adjacent combat remain guarded; survival runs first.
This deliberately accepts oklob exposure to enter the required branch, not a
claim that the excluded area is harmless.15 Lua suites/9 runner tests pass.

Verified from SAME saved position: confirmed console, CMD_SAVE_GAME_NOW,
archived checkpoint, stopped old process, restarted same character with
commit7c9e99e RC. Socket was already cleaned up by process exit; attempted
archive move reported missing and no socket deletion was needed. Entered Lair1
at13469 (21 turns after blocked state), continued naturally, then died to a
basilisk13645. Saved immutable continuation morgue and diagnostic metadata.
Original five-seed row remains paused; this resumed/fixed character is NOT a
fresh autonomous full-seed trial. No manual attacks/movement were supplied.

Seed3 death review (no Sigmund policy edits this turn):
- Encountered Sigmund2959; lure actions2960–2961 at49/56 then50/56HP.
- Unseen-attacker messages explicitly show hits followed by repeated poisoning.
  Exact weapon brand not recorded; do not claim a particular venom weapon.
- Natasha joined2966. Trog's Hand used during this sequence; regeneration
  and willpower did not keep pace with incoming hits/poison. Natasha killed2972.
- Same turn a something-hit8 left2/56HP. At2973 controller again chose
  "closing to marked disturbance" and succumbed to Sigmund's poison. Final
  poison projection was lethally negative. This was NOT a rest-in-steam death.
- Final inventory: no curing, heal wounds, teleport, fear or wands. Four
  teleport scrolls had been used atXL1–3 and two fear atXL4–6 (exact earlier
  encounters not reconstructed). No potion quaffs recorded. Unknown blinking,
  fog and silence remained, unusable by the known-only consumable policy.
  Scarf of invisibility was in inventory, not equipped.

Thus no ignored identified antidote is demonstrated. The two actionable
policy concerns are lure steps spent against a ranged invisibility-capable
unique, and marked-disturbance closing overriding the need to disengage while
already badly poisoned. Last action hastened poison ticking but2HP with lethal
poison was already critical; evidence does not establish a guaranteed escape.
This is message/notes/source reconstruction, not a new single-turn replay.

## Sigmund encounter experiments on seed3

Implemented sigmund_mode:0 existing,1 skip generic lure while remembered caster
is Sigmund,2 also force visible closing and allow berserk from two tiles at
>=55%HP,3 instead prioritize upstairs withdrawal while Sigmund is unseen.
The withdrawal experiment is capped at12 steps and does not chase disturbances
after that; other visible combat can act. Known consumables and Trog's Hand
still run first. All new behavior is Sigmund-only.16 Lua suites/9 runner tests
pass (no-lure gate, early-rage floor, unseen withdrawal/cap and name scoping).

Three fresh parallel runs on seed1760771545328102746 from commitdfd5e4a,
using separate immutable tactic snapshots in verified finished sessions:

| Policy | Sigmund outcome | Subsequent outcome |
| --- | --- | --- |
| Previous lure baseline | poison death2973, Natasha joined2966 | D3 death |
| No lure, CodexSigNoLure1 | killed2966; Natasha only arrived2974 | D11 orc wizard flame death12720,XL11 |
| Charge/rage, CodexSigCharge1 | closed2960–2962, berserk2963, killed2965 | D7 orc warrior halberd death7738,XL9 |
| Withdraw unseen, CodexSigWithdraw1 | killed2966; special withdrawal NEVER fired | Same D11 death12720 as no-lure |

The no-lure intervention is smallest and separates Sigmund/Natasha in these
replays. Withdrawal variant provides no live evidence for its unseen policy,
since the shared no-lure change already resolves the encounter. Do not claim
that this solves arbitrary invisible enemies or proves a particular RNG cause.
Independent fresh no-lure repeat launched as CodexSigNoLure2, same exact snapshot.
Canonical default selected mode1; SHA0768a5506e95c5f048ec6f88ccb6705103e08a00ae31b25950dee3a06a1752aa
matches both no-lure snapshots. No mid-run changes to snapshots or manual
tactical input. Full five-seed regression remains untested for this selection.

Repeat completed naturally: Sigmund killed2966 again; Natasha arrived2974 and
was killed3033. Continued through Lair and died in Orc2 to a smoke demon's
incineration at20885 turns,XL13. All four fresh trials reached terminal deaths
without intervention. The two identical no-lure snapshots reproduce the target
encounter success but diverge later (D11 versus Orc2); later progression is not
deterministic evidence of a policy improvement. Keep mode1 as the smallest
successful scoped change. Evidence morgues and all four result rows retained.

## Sigmund no-lure full five-seed regression

Batch sigmund-nolure-full-v1, source1622f09, clean canonical RC
0768a5506e95c5f048ec6f88ccb6705103e08a00ae31b25950dee3a06a1752aa,
same engine54cdf44895903fa3c7ac51278afff390d1bffe6f1abd581dc3529aa47a3d3b38.
Five fresh characters in reused verified-dead sessions. Seed4 used support4:
bench4's intervened continuation does not qualify for automatic runner reuse.
No gameplay intervention or mid-run policy changes. At seed2's explicit route
pause, entered and visually verified Lua interpreter, ran crawl.dump_char(),
then exited interpreter; no game turn advanced. Character remains paused.

| Seed | Previous lure-ally-full-v1 | Current | Turns / XL | Cause |
| --- | --- | --- | --- | --- |
| 1 | D11 death | D11 death | 10287 / 11 | centaur warrior arrow11 |
| 2 | D15 death | Shoals2 PAUSED | 27837 / 16 | travel to Shoals3 made no progress |
| 3 | D3 death | D11 death | 12720 / 11 | orc wizard puff of flame8 |
| 4 | D11 PAUSED | Lair1 death | 13741 / 11 | cane toad18 |
| 5 | D6 death | D6 death | 2336 / 5 | Pikel's lemure5 |

Seed3 again killed Sigmund2966. Seed4 entered Lair1 at13469, confirming the
required-entrance fix in a fresh autonomous run (not just the prior continuation).
Seed2 visited Lair1–5 and Orc1–2 before D15/Shoals. At full158HP on Shoals2,
repeated Unknown command / Done exploring messages preceded the explicit route
block. This is an unresolved navigation failure, NOT a successful terminal run.
Four deaths, one pause; no completion/clear claim. Exact clear prefix unmeasured.
Screen Time28983.4 is elapsed game time; dump's actual turn count is27837.

Reached ranks [11,24,11,12,6], paired changes [0,+2,+8,+1,0]. Observed minimum
rose3→6 versus preceding lure batch, but batch still fails autonomous completion
and remains below older wand-mesmerism minimum7. Seed5 is now the weakest:
unchanged D3 shaft to D6 followed by Pikel/lemure death. One run per seed is only
a screening comparison; this batch includes both entrance and Sigmund fixes.
All five evidence dumps and append-only result rows retained.

## Shoals disconnected-pocket routing fix

Read-only map inspection at paused27837 showed only upstairs/hatches in known
Shoals2 and no downstairs. ROUTE_STATE marked this pocket clear; native GA3
correctly selected Shoals3 but reported no known path. Branch hotkey A is valid
in the local engine. Repeated Unknown command messages are not evidence that
the branch key was wrong. Autoexplore completion described the reachable pocket,
not all disconnected regions of Shoals2.

Added bounded alternate-stair recovery: when same-branch next-floor travel fails
from a cleared floor with no known downstairs, return to the accepted parent
floor and try other normal stair sets, each at most once. On re-entry explore
again; when downstairs appears invalidate pocket-clear state and resume normal
exploration. Existing combat/movement-safety checks remain, and exhaustion of
safe alternatives pauses instead of looping. Parent may be partial only when
the configured route already permits partial progression. Recovery state saves
with the character; phase transitions now create persistent notes.

Initial commit635d12a did not activate on this save because the parent was not
marked clear. Follow-up2a25327 accepts configured partial parents.17 Lua suites
and9 runner tests pass, including alternate stair selection, re-entry invalidation,
combat guard, exhausted alternatives and partial-parent integration.

Same paused character saved via verified Lua interpreter, checkpoint archived,
restarted in same session. Corrected continuation naturally died28293 to kraken
tentacle16 on Shoals2. Repeated from original checkpoint with added notes:
- recovery starts27837;
- alternate downstairs ii from Shoals1 at28030;
- back upstairs from dead-end Shoals2 at28032;
- alternate downstairs i at28044;
- Shoals2 downstairs discovered28046; resumes exploration;
- kills a kraken28089, later dies to another kraken's tentacle28293.

Thus the exact navigation stall is resolved twice; this does NOT verify entry
to Shoals3 or rune collection, because combat killed the character first.
Saved both morgues and diagnostic metadata under interventions. Original full
batch seed2 row remains PAUSED; these checkpoint continuations are not fresh
full-seed benchmark replacements. Final tested RC SHA
b6c299f2593ccf8029bbc90b291741bc38b564eb61c681b5c45272444705fabd.

## Fresh five-seed repeat with Shoals pocket fix

shoals-pocket-full-v1 from clean RC at efb1b51, RC SHA
b6c299f2593ccf8029bbc90b291741bc38b564eb61c681b5c45272444705fabd,
same engine54cdf44895903fa3c7ac51278afff390d1bffe6f1abd581dc3529aa47a3d3b38.
Reused the five named sessions. For support2, verified diagnostic character's
death dump, no save, process identity and postmortem screen before closing it;
original benchmark paused row remains unchanged. Initial start preflight raced
process shutdown, refused without launching any games; after confirmed shutdown
the same config launched normally. All five fresh games ran without gameplay
input, RC changes or checkpoint intervention and reached natural deaths.

| Seed | Previous no-lure full batch | New | Turns / XL | Cause |
| --- | --- | --- | --- | --- |
| 1 | D11 death10287 | D11 death | 10287 / 11 | centaur warrior arrow11 |
| 2 | Shoals2 paused27837 | Lair2 death | 12169 / 12 | rime drake icy flash freeze17 |
| 3 | D11 death12720 | Lair5 death | 17500 / 13 | cyan ugly thing13 |
| 4 | Lair1 death13741 | Lair1 death | 13741 / 11 | cane toad18 |
| 5 | D6 death2336 | D6 death | 2336 / 5 | Pikel's lemure5 |

Seeds1/4/5 match previous death floor, turn and cause. Seed3 killed Sigmund2966
again. Seed2's first differing notes (ignoring character-name line) are already
on D8: old lure7103 vs new lure7124–7125/hold7126, after matching altar6968.
No Route pocket notes in ANY of the five dumps: this batch never exercised
the new recovery, and does not independently verify passage through Shoals.
It also does not establish that the pocket policy caused seed2's earlier death;
full action trajectories are not deterministic from the seed alone.

Reached ranks [11,13,16,12,6], paired changes vs previous [0,-11,+5,0,0].
Minimum remains6 (seed5), below older wand-mesmerism minimum7. All5 autonomous
terminal deaths, no pauses/observed stalls, no clear-prefix claims. Therefore
not the same results overall and not an improvement in the weakest-seed metric.
Saved all five immutable morgues and append-only benchmark rows.

## Pre-departure shopping policy

Added one shopping pass per accepted floor completion, before route progression.
Catalogues at most8 visited shops using bot waypoints0–7 (9 remains recovery
anchor); catalogue and departure-check state persist in ROUTE_STATE. Native
G<waypoint> provides interlevel fast travel. Re-evaluates affordability, inventory
need and live stock at arrival; at most4 purchases and300 elapsed turns per pass.
Ordinary combat interrupts and may resume after healing; disengage, confusion,
unseen-threat warning, unsafe travel, no-route message, two no-progress retries
or budget exhaustion abort the pass without retrying that departure. Route
progression cannot compete while shopping owns travel.

Known-only reserves: curing3, heal wounds2, teleport2, blink1, fear1, identify2
(identification only with unknown consumables). Reject stacks exceeding reserve.
Known axe/armour upgrades use existing scorers, exceed held gear by0.5 and leave
100gold; no shields, hard helmets for MiBe, or auxiliary gear displacing Lear's.
No jewellery policy yet. This is deliberately conservative, not optimal shopping.

Live shopping-v1 exposed a menu bug: shop_inventory returns raw stock order but
ShopMenu::resort reassigns letters. Seed1 unintentionally bought spell parchments
and a robe, in addition to a teleport scroll; reject this as valid purchase-policy
evidence. Seed1 died naturally; seed4 entered a repeated D6 lure/heal cycle and
was manually paused/saved after verified console entry. Its paused row is an
operator-ended diagnostic, not a native routing pause or completed benchmark.

Correction cc2778e: enter shop, '/' selects price order, derive rank across ALL
stock, skip equal-price ties because C++ ordering there is not guaranteed.
Fresh shopping-v2 seed1 bought exactly one teleport scroll for33gold on D1 at1379,
no unintended purchases. Continued to Lair3, then repeated lure/heal against a
centaur. Verified console inspection showed shopping.active=false, so shopping
was not the active loop. Read-only dump followed by resumed play; later manually
paused/dumped/saved at the same loop for future encounter debugging. No manual
combat or movement. Preserved corrected and incorrect evidence separately.

Final f81179e adds exact-cost verification and prevents isolated-enemy route
shortcut from competing with active shopping; tested in unit suites but not yet
another fresh live run.18 Lua suites/9 runner tests pass: price-order mapping,
tie rejection, reserves, combat interruption, disengage/no-route abort, bounded
no-progress/elapsed-turn retries and route ownership. Shopping purchase works in
live play; safe abort paths are unit-verified, not all exercised in live combat.
Full five-seed regression and autonomous completion remain unverified.

## Centaur lure/heal loop fix

Cause in approach_action: ranged detection preceded the mode2 backstep block,
but its early return came AFTER that block. Thus even a known shooter received
a lure step. Losing LOS then healing beyond encounter_memory caused idle; the
next sighting reset e.approach and restored the lure budget. Repeated same-area
lure/recover/idle cycles were observed in the saved Lair3 centaur encounter.

582f667 moves the ranged return ahead of all preparation backsteps. Conservative
unknown ranges already count as ranged. Genuine encounter disengagement remains
separate; melee-only lure budgets remain unchanged. Regression reproduces a
valid mode2 backstep path, then checks ranged rejection through three encounter
resets.18 Lua suites and9 runner tests pass.

Archived CodexShopPrice1 saved checkpoint at18039 Lair3 HP117, restarted same
session with exact RC SHA6322f30438ef1467fd3a5f930a9f27a36478a7c734aca591e7fb6ab0fe6e3261.
No manual gameplay input. Character left the loop, progressed through Lair4–5
and Orc1–2, then was banished and died naturally in Abyss2 at23165 to a
cognitogaunt's psychic fangs8. Saved immutable morgue and intervention metadata.
This verifies escape from the target stall, not guaranteed survival against
ranged threats or all lure loops. The restarted RC also contains the previously
unit-tested shopping ownership/cost guards. Original shopping-v2 paused result
is preserved; this continuation is not a fresh fixed-seed benchmark replacement.

## Simple Abyss escape policy

3e02dac introduces an Abyss-only controller before ordinary encounter/routing
logic. Abandons shopping, prioritizes actual exit_abyss features with one-step
pathfinding, otherwise keeps moving with a simple nearby-enemy danger penalty
and heading/frontier preference. No normal Tab pursuit, floor completion, or
intentional Abyss descent; attacks adjacent blockers only when boxed in.
Uses emergency healing, teleport, fear/fog; 53a6250 adds targeted emergency
blink, c23dd47 adds low-health invisibility. 666036f confirms the invisibility
potion activation preview before generic input cancellation guards. On return,
clears Abyss encounter/recovery state and resumes the ordinary route.

Repeated the same archived Lair3 turn18039 checkpoint in codex-support1 four
times, with no manual combat/movement and no forced banishment. All reached
Sonja's direct banishment into Abyss2 at23069 (not a bot descent). Initial policy
died23193 to purple draconian shifter; blink revision used blink23168 but died
23171 to white draconian stormcaller. Invisibility revision died23172 to laughing
skull and exposed a cancelled activation preview/pending-input error, so it is
not valid evidence of successful consumable integration.

Final replay: exit approach23144, take exit23149, native Escaped the Abyss note
23150 Orc2, normal-controller return note23151. Spent81 turns in Abyss; killed
Sonja23171 and continued autonomously to natural centaur-warrior death23934 D13.
Final morgue's DLua errors section is empty. This verifies finding/taking an
exit and resuming progression in this replay, not guaranteed Abyss survival or
that invisibility caused success. Retained all four morgues and metadata under
abyss-escape-resume-v*. Original paused benchmark row remains unchanged.

19 Lua suites and9 runner tests pass, including exact exit vs deeper stair vs
stone arch, enemy avoidance, adjacent-blocker attack, return-state cleanup, and
invisibility preview confirmation. No fresh five-seed regression this turn.

## Current-RC full batch and throwing assessment (abyss-full-v1)

Fresh five-seed run of source938805c, unchanged RC
7635fba5c84678204601aa19e8b9363a8505a0a2e24d82c6e8d063a5cfabd4f8.
All five ended naturally, no manual gameplay intervention or pauses. Reused
verified-dead codex-bench5; runner rejected unverifiable old bench1–4 sessions,
so preserved those and used new codex-verify1–4. Immutable snapshots/manifests,
five morgues and append-only rows retained. No RC implementation changes here.

Seed | Prior shoals-pocket-full-v1 | Current | Turns | Final encounter
--- | --- | --- | --- | ---
1 | D11 | Lair2 | 11835 | Skyshark and blink frog; skyshark final blow
2 | Lair2 | D9 | 7529 | Many yaks plus killer bees/poison; yak final blow
3 | Lair5 | D4 | 3546 | Eustachio and summons; iron imp final blow
4 | Lair1 | D5 | 4319 | Repeated curare darts from kobold brigand; curing exhausted
5 | D6 | D5 | 4898 | Gnoll bouda healing gnoll while bot trades weak attacks

Minimum reached rank regresses6->4. Paired route-rank deltas +2,-4,-12,-7,-1.
Seed5 is XL8 at death vs XL5 previously, despite the lower reached floor;
reached-depth metric is not experience or confirmed clearing. No Abyss visit in
this batch, so these deaths do not isolate a regression in the Abyss controller.
Changes since the comparison include shopping and the ranged-lure fix; action
trajectories diverged. Do not assign causal blame without paired diagnostics.

Throwing availability: seed1 carried5 throwing nets; seeds2–5 have no Missiles
inventory section. None records a Throw action. This is carried inventory at
death, NOT a census of floor items or shop stock: uncollected darts/boomerangs/
javelins cannot be quantified from these morgues. No explicit missile selection
in pickup_for_bot, and update_skills disables Throwing. Current evidence does
not justify assuming abundant ammunition or investing heavily in Throwing.

Small proposed experiment (not implemented): collect bounded nets/curare and log
seen ammunition; use one targeted control throw before melee/berserk against a
visible eligible dangerous enemy, then reassess. Require clear friendly-safe
trajectory, vulnerability check, and no redundant throw at an already-controlled
target. Never replace emergency healing/escape with a speculative low-HP throw.
Curare's monster effect in this engine (beam.cc:_curare_hits_monster) checks
poison resistance and supplies poison, 2d6 damage and slow unless stasis; it
still requires a hit. Atropa/datura success depends on Throwing+Stealth versus
HD (throw.cc:_get_dart_chance), making them a poor initial zero-training policy.
General boomerang/javelin damage should be a separate ammo/training experiment.

Resource handling remains at least as important: seed1 died with blink, fog,
invisibility, charged wands and enchantment scrolls; seed4 had4 identify scrolls
with heal wounds/might/invisibility still unknown at death. These inventories
suggest opportunities but do not prove legality/usefulness on the final turn.

## Throwing first pass (throwing-full-v1)

914cbbb adds pickup of nets/darts/javelins/boomerangs and enables Throwing with
target4 alongside existing skills after eligible ammunition is held. Safe-time
skill updates detect acquisition; no training for merely spotted items. Yellow
preparation uses boomerangs; red targets prefer curare unless poison-resistant
or already slow/poisoned. Three TOTAL spent throws per encounter, including
curare attempts, reset with normal encounter lifecycle; same-turn rejection
guard. Uses explicit F item menu and player-relative target. Conservative clear
shot rectangle, reachable visible target <=7 tiles, no adjacent hostile, no
berserk/confusion/cooldown/movement lock/unseen warning or disengage. Earlier
survival, recovery and positioning retain priority. Nets/other darts/javelins
are collected but not thrown. No autonomous ammo retrieval added.

20 Lua suites and9 runner tests pass. Throw suite checks boomerang input,
curare preference, already-poisoned fallback, three-shot cap, same-turn retry,
disengage, obstruction and adjacent hostile veto. Live notes/action tables
verify boomerang firing, three-shot cap and target4 reached. No live curare
throw occurred, so curare input/effect integration remains unverified.

Same five sessions reset via runner, unchanged snapshot
a9b08ab54c55a194e93c9dc33c39ee99cc28a605b638bc9527f17875f2760523.
Seed | Previous abyss-full-v1 | Throwing | Outcome | Boomerang throws
--- | --- | --- | --- | ---
1 | Lair2 | D11 | Centaur arrow death7830 | 17
2 | D9 | D12 after Lair5 | Pyromancer liquid-fire death16524 | 31
3 | D4 | D4 | Eustachio iron-imp death3546, unchanged | 0
4 | D5 | D6 | Native unresolved-unseen-threat recovery pause6106 | 3
5 | D5 | D5 | Bombardier beetle liquid-fire death4152 | 7

Four natural deaths, one native pause (not a successful autonomous completion).
Seed4 killed steam dragon then paused with orc priest/marrowcuda visible,
HP63/106 while berserk. Verified console entry, read-only dump, then saved with
Ctrl-S; no manual combat/movement. Save remains CodexThrowFull4.cs. Recorded
paused row and immutable dump, not death. Other games had no intervention.
All five dumps have empty DLua error sections. No full-batch success: minimum
reached rank remains4 and seed1 regresses; seed2 improves substantially but
this does not isolate throwing damage from training/RNG trajectory changes.

Seed3 collected no ammunition and repeats exactly the earlier death. The other
four collected ammunition;58 total boomerang throws. Seed4/2 hold curare but
never used it in this run. Next priorities: liquid-fire handling (both seed2
and5 killed the source but continued burning to death) and the existing D6
isolated-recovery pause. Keep these results separate from a future fix batch.

## Liquid-fire movement and unseen-recovery continuation

2cbd5c4: liquid_fire_action precedes ordinary survival/combat/rest. While on
fire it selects a visible unoccupied legal safe step, penalizing proximity to
hostiles, respecting existing cloud/exclusion/mesmerisation checks. Below25%
HP tries known heal wounds first; immobile/confused/boxed-in cases retain normal
emergency handling. Engine player.cc:shake_off_sticky_flame removes60 duration
per actual move; stationary recovery did not do this. Hazard-wait no longer
preempts fire movement. No forced movement into unsafe squares.

Unseen isolated recovery previously returnedfalse, then isolated_enemy_action
latched BOT.paused. Now treats unseen activity as hazardous, still prefers a
known recovery anchor path, then a cautious legal step, else one real WAIT to
rebuild cloud/visibility/path information next turn. Does not custom-explore or
permanently pause on this path. A boxed-in character can still take damage;
this change is continued reevaluation, not a guarantee of escape.

Saved seed4 resumed at6106 D6 HP63/106 in the same session with archived save
and immutable RC37897805d4ead08eb8c018dafc3dbd1c5855e5dbe02ac179a075bfbeabdeb84c.
No manual combat/movement. Cleared target pause, reached D7 then D8 and died
8876 to gnoll-sergeant poison. Saved continuation evidence/metadata separately;
original throwing-full-v1 paused row preserved.

Fresh affected seeds (fire-recovery-v1, same RC/source):
- Seed5: prior D5 burning death4152 -> D10 Sonja-poison death9847. Live shake-off
  notes6307–6311 on D7 HP78,74,71,72,68; survived that liquid-fire episode and
  continued. Earlier D5 encounter trajectory differed, so not an exact replay
  of the original fatal beetle actions.
- Seed2: prior D12 pyromancer burning death16524 -> D12 Frances iron-shot38
  death16569. No liquid-fire action notes; this rerun did not reproduce the
  original burning episode, so it is not direct verification of that encounter.

21 Lua suites and9 runner tests pass. New tests cover fire movement vs ordinary
rest, occupied/unsafe destinations, and unseen/blocked recovery returning a real
action without pausing. Live fire movement verified on seed5 and pause escape
on saved seed4. No full five-seed regression or general survival claim.

## Full replay after fire/recovery fixes (fire-recovery-full-v1)

Fresh five seeds, unchanged current RC37897805d4ead08eb8c018dafc3dbd1c5855e5dbe02ac179a075bfbeabdeb84c,
sourcecbea9a7. Reused same five sessions; seed4 prior checkpoint continuation
death was separately verified against morgue/process/no-save/postmortem screen
before resetting its session. No gameplay intervention in the new runs except
dump/save after seed4's native route pause.21 Lua suites/9 runner tests pass.

Seed | Prior throwing-full-v1 | Current | Outcome
--- | --- | --- | ---
1 | D11 death7830 | D11 death7830 | Centaur arrow; unchanged
2 | D12 death16524 | D12 death16769 | Frances iron shot24, after Lair5
3 | D4 death3546 | D4 death3546 | Eustachio iron imp; unchanged
4 | D6 pause6106 | D11 pause11558 | Lair entrance not discovered
5 | D5 burning death4152 | D8 death7719 | Two-headed ogre plus rock fish

Four natural deaths, one native pause; no verified route completion. Weakest
reached milestone remainsD4. Seed4 and5 advance farther, seed1/2/3 milestones
unchanged, but the batch is still not fully autonomous because of seed4.
All five DLua error sections empty. Seed5 has shake-off notes on D5 at4128–4136
and D7 at6484–6493, survived both; no lingering-fire death. Seed2 died to Frances
rather than burning, with no fire-action notes. No return of the D6 recovery
pause in fresh seed4; instead D11 reported partly explored/cannot reach places,
then stage complete and route blocked: entrance to Lair not discovered. Do not
interpret this stage-complete message as verified full D11 exploration.

Saved seed4 at11558 D11 HP90/90 after verified console entry/read-only dump,
Escape and Ctrl-S, without manual movement/combat. Save CodexRecoveryFull4.cs
available for route diagnosis. Immutable evidence and append-only rows retained.
Next priorities: diagnose missing-Lair route pause from this save, then weakest
seed3's unchanged Eustachio summon-pack death. This run does not establish an
improved minimum or statistical reliability of the individual gains.
