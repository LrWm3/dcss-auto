# Optional slow-ogre experiment (queued)

This isolated snapshot leaves the main healing suite and its source hashes
unchanged. `origin.json` records the copied source hashes. The six-condition
30M seed-0 screen is queued after the main healing suite; smoke runs are
implementation checks only. N=2 stress tests and erase-tool runs are not queued.

Queue log: `gpu-d1/results/ogre-feature-screen-30m-console.log`.
To resume the queued suite, use the same entry point (which includes its own
source hash in the manifest):

```sh
gpu-d1/.venv/bin/python -u gpu-d1/branches/ogre-v1/scripts/queue_after.py \
  --after-suite gpu-d1/learning-runs/route-healing-30m \
  --steps 30000000 --seeds 0 \
  --output gpu-d1/learning-runs/ogre-feature-screen-30m
```

## Task and simulator rules

- Clear 24 ordinary enemies on the existing 256 training layouts, within 1024
  turns. Validate on the existing 32 layouts; keep the 100 test layouts reserved.
- Add N=0, 1 or 2 optional ogres. Clearing succeeds as soon as the 24 ordinary
  enemies die, even with ogres alive. Ordinary kills earn +1; optional ogre kills
  earn zero. Clear +3, death -1, turn -0.001, new floor +0.002 remain unchanged.
- Ogre starting HP is 48. Its proxy attack kind is speed=5, damage=24,
  to-hit=30, shield-bypass parameter=25. These are provisional experiment
  settings, not a faithful native Crawl ogre. Armour, evasion, shields and
  attack randomness still apply, so 24 is the pre-mitigation damage ceiling.
- Ogres use the **same energy scheduler** as other monsters. Speed 5 adds five
  energy per player turn; actions cost ten and require energy >=80. Sleep and
  wake behaviour are unchanged: wake within six tiles, energy set to 70.
  This normally gives an action every other turn after waking, while preserving
  the existing handling of any extra energy. No separate turn gate is used.
- Each ogre spawns at Chebyshev distance >=12 from the player, on an unoccupied
  floor square. This also lower-bounds the number of eight-way movement steps.
  A separate cloned spawn RNG keeps initial player and ordinary encounters
  identical across N; the first ogre also matches between N=1 and N=2. Subsequent
  trajectories and shared combat RNG naturally diverge.
- `spawn-preflight.json` verifies enough distant squares for every possible
  player start on all 288 training/validation maps, even after other placements.
  Existing terrain and distance tables are reused; no new all-pairs distances
  or per-episode layouts are stored.

## Information ablations

All models have 741 inputs, 9 primitive actions and the same two 128-unit hidden
layers. Inputs retain the existing local view, remembered ring, known frontier,
route cue, player state and global enemy HP/location/type records. Every live
enemy has an explicit required-for-clear bit. Ogres get a distinct type code.
Thus the baseline can identify optional targets even without extra stats.

Eight feature slots per monster are reserved in every variant (40 slots):
required, awake, speed/10, max-HP/48, damage/24, to-hit/30, bypass/25, readiness.
Unused/dead records are zero. Required is always exposed; the rest are masked
according to the variant, preserving parameter count and initialization.

| Suffix | Additional information |
| --- | --- |
| `base` | None beyond required bit and existing HP/type/location |
| `awake` | Awake/asleep bit |
| `speed` | Actual configured speed |
| `stats` | Maximum HP, damage, to-hit and bypass; excludes speed/awake |
| `all` | Awake + speed + stats |
| `all_timing` | All above plus whether an already-awake enemy has enough energy to act after the next increment |

Readiness is a privileged scheduler diagnostic: it does not predict intervening
death, movement, wake-up or exact number of actions. The first screen uses N=1:
`ogre0_base,ogre1_base,ogre1_awake,ogre1_speed,ogre1_stats,ogre1_all`.
At 30M each this is 180M decisions. N=2 variants are available as a subsequent
stress test; start with `ogre2_base,ogre2_all`. N=0 with all features is also
available to check whether features help ordinary combat even without ogres.

These are **global** enemy inputs, matching the current task. This is not a
visibility-limited experiment. Fixed types, known roles and fixed stats mean
the ablation tests whether explicit numerical information helps learning, not
generalization to arbitrary unseen monster stats. Slot order can also encode
role; a later shuffled-record or shared-encoder experiment would address that.

## Running and measurement

```sh
# Review the six-condition screen without starting training.
gpu-d1/.venv/bin/python gpu-d1/branches/ogre-v1/scripts/run_ring_ablations.py \
  --steps 30000000 --seeds 0 --dry-run

# Launch when wanted; uses the shared original corpus by default.
gpu-d1/.venv/bin/python -u gpu-d1/branches/ogre-v1/scripts/run_ring_ablations.py \
  --steps 30000000 --seeds 0 \
  --output gpu-d1/learning-runs/ogre-feature-screen-30m
```

Record sampled and greedy clears, required kills, deaths and timeouts, plus
optional ogre kills, ogre damage, ogre actions, turns adjacent to an ogre,
living/awake ogres at termination and deaths directly inflicted by ogres.
The latter is a cause-of-final-hit statistic, not proof of avoidability.
Per-map results, 0/1M/3M/10M/30M checkpoints and training seconds are retained.
Compare matching decision budgets, then repeat promising conditions over seeds.
Results cannot be ranked directly against the old 40-required-enemy task.

The existing 2 GiB output cap, 5 GiB free reserve and latest/best checkpoint
retention apply. All new native state counters are included in restart saves.

## Later erase-tool phase (design only; not implemented)

Use the selected N=1/2 setting and chosen representation. Provide K=N+M charges
for M=0/1/2, with a K=0 control. Each consumable erases one chosen living enemy;
include target choice so the environment does not automatically select ogres.
Expose charges remaining, use one turn, then let surviving monsters act.
Ordinary erasures count toward the required 24; ogre erasures remove a threat
without advancing the clear counter. Preserve normal kill-reward distinctions.

Define and test targeting visibility before implementation. The current local
9x9 view includes cells behind walls; using its visibility proxy is different
from native line of sight and must be explicit. Mask invisible/dead targets.
Suggested measurements: target type per use, charges left at death, required
and optional targets erased, HP and nearby threats at use, and final clears.
This will distinguish resource allocation from merely granting more power.

## Verification completed

- Native fixtures passed for every feature mask: distant/unoccupied spawning,
  speed-5 cadence, multiple actions with boosted energy, optional-kill rewards,
  role/stat fields, clearing with living ogres, and reset counters.
- All 288 training/validation maps passed spawn preflight. The smallest number
  of distant floor candidates for any start was 253, above the conservative
  requirement of 26.
- N=0/1/2 end-to-end smoke training, evaluation and checkpoint saving passed.
- CPU/CUDA outputs, observations and masks matched over 1,050 transitions per
  ogre count; initial ordinary enemies and player placements matched across N.
- Interrupted-resume training exactly matched uninterrupted training for
  policy, optimizer, native state, observations, RNG and evaluation.
- The active main healing suite's source hashes remain unchanged.

Smoke artifacts: `/tmp/ogre-branch-smoke` (not learning results).
Native fixture: `src/test_ogres.cu`. Trajectory comparison:
`scripts/test_ogre_parity.py /tmp/ogre-branch-smoke`. Resume check:
`scripts/test_ablation_resume.py /tmp/ogre-branch-smoke ogre1_all`.

Performance: fresh runner suites default to `--performance fast`; `--performance reference` retains the original computation path. See [shared performance report](../../PERFORMANCE.md). Old result directories require an explicit migration or a fresh output path after source changes.
