# Frozen broader evaluation — 2026-09-09

The selector recovered in **45/49 encounters (91.8%)**, versus **47/49 (95.9%)**
for fixed pursuit with berserk permitted. These results do not justify replacing
the fixed controllers with the learned selector yet.

The model and controller code were frozen throughout. No training or production
deployment occurred. All cases were absent from this model's original training
and validation sets. They are historical checkpoints on D:1–D:7, not fresh
full-game rollouts or independent samples from 49 seeds.

## Results

| Strategy | Unused-by-model seeds (24 cases) | New cases on familiar seeds (25 cases) |
| --- | --- | --- |
| Selector | 23 recovered, 1 death | 22 recovered, 2 deaths, 1 parser error* |
| Withdraw, no berserk | 20 recovered, 4 unavailable | 22 recovered, 1 death, 1 unavailable, 1 startup error† |
| Withdraw, berserk permitted | 20 recovered, 4 unavailable | 23 recovered, 1 death, 1 unavailable |
| Defend, no berserk | 23 recovered, 1 death | 21 recovered, 3 deaths, 1 unavailable |
| Defend, berserk permitted | 22 recovered, 2 deaths | 21 recovered, 2 deaths, 1 unavailable, 1 parser error* |
| Pursue, no berserk | 21 recovered, 3 deaths | 23 recovered, 2 deaths |
| Pursue, berserk permitted | 23 recovered, 1 death | 24 recovered, 1 death |

\* Both parser errors are **morgue-confirmed poison deaths** on the same D:7
checkpoint, including identical morgue contents. Raw results remain unchanged.
Thus the selector's observed game outcomes are 45 recoveries and four deaths,
not three deaths plus a potentially surviving character.

† A fixed-withdrawal trial exited before its first decision with a Lair map-parser
error. A separately logged retry with unchanged source/checkpoint recovered in
26 decisions. The retry does not overwrite or enter the primary table.

Withdrawal's available-only denominator differs from pursuit's: do not compare
its rate directly to a policy that must handle all 49 cases. There is at least
one recovered fixed option on every checkpoint; that is an after-the-fact upper
bound, not an implemented policy or a guarantee of future success.

Selector results by seed:

| Seed | Recovery |
| --- | --- |
| 83017001 | 6/6 |
| 83017002 | 5/5 |
| 83017004 (reserved test) | 6/6 |
| 83017005 | 5/5 |
| 83018001 | 6/6 |
| 83018002 | 5/5 |
| 83018003 | 5/5 |
| 83018004 | 2/5 |
| 83018005 | 5/6 |

Unused-by-model seeds: 83017001, 83017004, 83018001, 83018005. The other five
seeds supplied training encounters previously, but none of these particular
evaluation cases entered training. Original seed partitions are unchanged.
The reserved test has now been inspected and must not be described as pristine
when evaluating future tuning.

## What failed

All case numbers below refer to `mining-fresh-training-v1/collection`.

1. **005, seed 83018005, D:2 gnolls — defend+berserk.** The controller waited
   at its defensive tile while a halberd gnoll attacked from two tiles away.
   At turn 1022, waiting reduced HP from 27 to 17. It waited again, then attempted
   berserk only when another gnoll became adjacent. Activation failed, HP fell
   to 5, and it eventually died. Both withdrawal variants and pursuit+berserk
   recovered. This is a defensive waiting defect, not merely unlucky activation.
2. **009, seed 83018004, D:2 Sigmund — defend without berserk.** A kobold fight
   revealed Sigmund. The controller then waited through ranged spells and
   two-tile scythe attacks, dropping from 33 to 17 HP before abandoning the hold.
   It retreated, Sigmund became invisible, and emergency teleportation began at
   8 HP. It died during the subsequent escape. Both withdrawal and pursuit
   variants recovered. It should reassess on the new ranged threat and damage,
   not exhaust a fixed lure allowance first.
3. **019, seed 83018004, D:7 Jeremiah / Blorkula / kobolds — defend+berserk.**
   It activated berserk against an adjacent orc while Jeremiah could smite from
   range, then waited with Jeremiah distant as berserk expired. Later movement
   and hazards led into Blorkula's bats and a poisoning kobold brigand. It used
   four mindburst casts against vampire bats late in the fight and succumbed to
   the brigand's poison on turn 6009. Defend without berserk and pursue+berserk
   recovered; withdrawal was unavailable. The trace motivates better ranged-threat
   assessment and berserk timing, but does not isolate one decision as the sole
   cause. The terminal death text was rendered as a partial redraw (`die...`),
   which the harness's literal `You die...` matcher missed. Separate death morgues
   prove death for both the selector and fixed defend+berserk runs.
4. **024, seed 83018004, D:6 Maggie — withdraw without berserk.** Withdrawal
   initially moved toward recorded stairs. Once mesmerised at turn 5003, it
   issued 20 consecutive safety actions instead of continuing tactical navigation.
   Apart from using haste, it mostly let Maggie cast and attack with a reaching
   halberd until death. Both pursuit variants recovered. Python delegates
   mesmerisation to `goal_safety`, but that restricted Lua handler has no active
   mesmerisation movement response; with no adjacent target or usable resource,
   it falls through to waiting. This shared hazard override can defeat any goal
   once the condition is entered.

## Recommended next iteration

1. Repair mesmerisation handling: choose a legal useful move, break line of sight
   where possible, or close and fight when escape is forbidden. Do not let a
   generic safety fallback monopolize every turn by waiting.
2. Make defensive holding conditional on actual safety from reach/ranged attacks.
   Damage or a newly revealed ranged threat should trigger immediate reassessment,
   not eight lure waits. Also review fallback dispatch: assigning withdrawal
   currently can fall through into a pursuit step in that same decision.
3. Revisit berserk timing when an adjacent weak enemy is accompanied by a distant
   caster. Permission need not imply activation at the first adjacent target.
4. Harden death detection using authenticated current-run terminal/morgue evidence;
   do not treat arbitrary timeouts or stale character dumps as deaths.
5. Re-test these controller fixes before collecting replacement labels or fitting
   new weights. Reserve prospectively fresh seeds for the next untouched evaluation.

These are recommendations, not changes made during this frozen evaluation.

## Integrity and artifacts

- All 49 derived reset checks matched parent observations and repeated resets.
- All 343 planned rows were recorded: 308 recoveries, 20 deaths, 12 masked choices,
  and three raw harness errors. There were 22,476 recorded controller decisions.
- Every one of the 308 recovery traces passed an independent replay of the
  full-health, no observable threat/harm, 20 consecutive checked quiet turns rule.
- All 49 selector outcomes matched their corresponding fixed combination's raw
  outcome, including the matched parser-error pair. Forty-eight pairs had normal
  terminal classifications; the remaining pair has matching poison-death morgues.
- No budget-truncated, no-turn-stall, or unresolved-stall outcomes occurred.
- Model, engine, production RC, dataset, and controller sources remain unchanged.

Artifacts: `artifacts/goals-broad-v1/` (`results.json`, `analysis.json`, `audit.json`,
`reset-checks.json`, trial traces, and separate startup-error retry).
Tracked evidence: `evidence/goals-broad-v1.json`.
Run instructions: [GOAL-CONTROLLERS.md](GOAL-CONTROLLERS.md#frozen-broader-evaluation).
