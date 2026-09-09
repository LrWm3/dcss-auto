# Controller fixes before retraining — 2026-09-09

This iteration changes the laboratory controllers and death-detection harness,
not the selector weights or production RC. Evaluation uses the same recovery
endpoint and budgets as `goals-broad-v1`.

## Changes

- Mesmerisation no longer delegates every turn to the passive safety fallback.
  The controller uses player-visible `view.withheld` flags to choose a legal,
  unoccupied, non-hazardous step toward a reachable enemy, then fights adjacent
  enemies. Berserk permission is still respected; emergency resources can preempt.
  When the condition ends, the original retreat destination remains available.
- Defense stops luring when damaged or exposed to a meaningful ranged/reaching
  enemy. The observation adapter exports the existing player-facing monster
  `range()` and `reach_range()` information. These do not enter model features.
  Weak stone-throwing enemies are not automatically reasons for a long retreat.
- Switching after an exhausted lure allowance to withdrawal now executes a
  withdrawal step immediately, instead of falling through into pursuit.
  Old pursuit counters cannot reverse
  an ongoing withdrawal when a new enemy appears.
- A missed terminal death message can be verified from the current reset's private
  death morgue. Character identity, seed, zero HP and non-stale turn must match.
  Ordinary dumps, timeouts and engine exits alone remain insufficient evidence.
- The evaluation runner requires an explicit `--revised-controllers` flag to use
  changed sources with the frozen model. It records both original and new source
  hashes, and supports exact `--case-id` restrictions. It never fits weights.

## Targeted iterations

The first pilot (`goals-fixes-pilot-v1`, source commit `141ca81`) recovered in
three of four previously fatal selector cases. It treated every two-tile enemy
as a possible reach user, which caused an early retreat from a kobold and still
lost to Sigmund. That heuristic was replaced with actual exposed attack ranges.
Its 28 rows were 20 recoveries, six deaths and two unavailable choices.

The refined pilot (`goals-fixes-pilot-v2`) recovered in all four selector cases:

| Case | Unchanged model choice | Revised execution |
| --- | --- | --- |
| D:2 gnolls, fresh005 | Defend + berserk permitted | Abandoned unsafe hold, ascended to D:1; 69 decisions |
| D:2 Sigmund, fresh009 | Defend, no berserk | Fought kobold, retreated earlier, handled confusion, ascended to D:1; 98 decisions |
| D:7 Jeremiah/Blorkula, fresh019 | Defend + berserk permitted | Abandoned ranged-exposed hold and fought; recovered on D:7 in 109 decisions |
| D:6 Maggie, fresh024 | Withdraw, no berserk | Three legal approach steps while mesmerised, fought, resumed withdrawal to D:5; 200 decisions |

All four derived reset checks passed. All 23 recovery traces in the refined
28-row pilot passed the full-health-plus-20-quiet-turn audit. Three fixed-choice
trials died and two choices were unavailable. In particular, fixed pursuit
without berserk still fails the D:7 encounter and now dies against Maggie;
improving the selected option does not mean every fixed option improved.

These four examples were explicitly used to tune the controllers, so their
successes are regression-test results, not held-out generalization evidence.
The broader run is likewise an inspected benchmark, not a pristine test set.

## Reproduction

```sh
/usr/bin/python3 .webtiles/bench/tactical/evaluate_goals.py \
  --revised-controllers --jobs 10 \
  --output .webtiles/bench/tactical/artifacts/goals-fixes-next
```

Outputs must be new directories. The frozen selector hash remains
`1f2b9cf7f525191cb4b2bf0c724bb95efdd43a26cf16db56befb9089d1efb7f0`.
Old source-bound training caches are deliberately rejected after the harness
change; do not bypass their provenance checks to reuse old labels.

The legal-approach controller is intentionally small. It does not guarantee an
escape from multiple beholders or route around every obstacle; when no useful
legal neighbor exists, bounded safety handling can still end unresolved.

## Completed broader comparison

The unchanged selector recovered **49/49**, up from **45/49**. All 49 selected
options and their input feature dictionaries were identical to the baseline.
All 49 selected outcomes matched the corresponding revised fixed-option replay.
The weakest prior seed, 83018004, improved from 2/5 to 5/5; 83018005 improved
from 5/6 to 6/6. The other seven seeds retained all their selector recoveries.

| Controller | Revised recovery | Unavailable |
| --- | --- | --- |
| Selector | 49/49 | 0 |
| Withdraw, no berserk | 44/44 available | 5 |
| Withdraw, berserk permitted | 44/44 available | 5 |
| Defend, no berserk | 46/48 available | 1 |
| Defend, berserk permitted | 48/48 available | 1 |
| Pursue, no berserk | 46/49 | 0 |
| Pursue, berserk permitted | 48/49 | 0 |

The reconciled 343 combinations contain 325 recoveries, six deaths and 12
unavailable choices, over 22,855 recorded controller decisions. No unresolved
stall, no-turn stall or budget truncation occurred. Availability denominators
differ: an always-withdraw policy does not cover all 49 cases.

Four fixed combinations changed from recovery to death:

- `mining-deeper-v1/collection/encounter-015`: pursue with berserk permitted.
- `mining-fresh-training-v1/collection/encounter-019`: defend without berserk.
- `mining-fresh-training-v1/collection/encounter-024`: pursue without berserk.
- `mining-fresh-training-v1/collection/encounter-030`: defend without berserk.

None was the selector's chosen combination. These regressions are retained,
not removed from the benchmark. They caution against treating the revised
controllers as universally better or assuming range-based retreat always helps.
Berserk activation timing itself was not separately retuned in this iteration.

### Startup errors and reconciliation

The main run recorded 336 rows after quarantining one failed parent startup.
Another trial exited before its first decision. Both printed the pre-existing
Lair `regret_index_lairdec_grave_grove` map-parser error, not a game death.
Two separate unchanged-source runs repeated the affected cases' reset checks and
all seven choices. Both produced seven recoveries. The combined comparison fills
the missing seven rows and replaces only the verified zero-decision startup-error
row; six duplicate completed outcomes agreed and are not counted twice.

All original files remain intact. The combined manifest records source/result
hashes, the replaced worker and duplicate agreement. Artifacts:

- `goals-fixes-broad-v2`: original 48-case execution and failed startup records.
- `goals-fixes-broad-v2-retry`, `goals-fixes-broad-v2-retry2`: explicit repeats.
- `goals-fixes-broad-v2-combined`: 49-case results, comparison and endpoint audit.
- `goals-fixes-death-regression`: old controller/RC with the new detector, which
  reproduced the previously missed poison death in 52 decisions and verified it
  from the death morgue. This diagnostic is excluded from new-controller scores.

No model fitting, dataset repartitioning, production deployment or engine change
occurred. These are now tuned historical regression cases, not an untouched test.
Fresh seed encounters and full-game integration should precede claims of broader
generalization; fitting again on an already solved benchmark adds little evidence.

All 325 successful traces passed the independent recovery-boundary audit.
Verification also passed 127 Python tests and 13 existing Lua checks.
Tracked provenance and comparison: [evidence/goals-fixes-v2.json](evidence/goals-fixes-v2.json).
