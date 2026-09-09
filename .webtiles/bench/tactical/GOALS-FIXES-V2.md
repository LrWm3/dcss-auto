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
- Switching from holding to withdrawal now executes a withdrawal step immediately,
  instead of falling through into pursuit. Old pursuit counters cannot reverse
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
