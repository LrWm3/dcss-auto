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
