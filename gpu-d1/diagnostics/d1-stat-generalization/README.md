# D1 stat and quantity generalization experiment

Status: implemented and running, 2026-09-17. The design below was committed
before implementation. Execution details and results are appended at the end.

## Question and starting point

Can the D1 exit policy adjust its behavior to player strength, enemy strength,
and encounter density, including combinations it never experienced in training?
Separate four claims: existing zero-shot robustness, improvement after varied
training, composition of familiar stat values in unfamiliar combinations, and
generalization beyond the training ranges. Success at one does not establish the
others. Also distinguish surviving by avoiding fights from becoming better at
fighting: leaving alive is the actual task.

Start all learned arms from the validation-selected broader-survival checkpoint:
`learning-runs/d1-stairs-survival-broad/targeted/checkpoints/3000320.pt`.
Retain the original adapted policy as an optional diagnostic, not another main
training arm. Keep three stairs, local 15x15 wall-blocked LOS, LOS-required waking,
MOVE/ATTACK/WAIT/REST/DESCEND, 2048 physical turns, and reward +1 on descent minus
0.00001 per physical turn. No XP, ogres, new rewards, or speed changes.

## Current implementation constraints

Source inspection of `branches/d1-stairs-v2` and its fixture establishes:

- Player maximum HP is 18. The observation contains current/max HP, but neither
  maximum HP nor player attack damage explicitly.
- Player attacks have 80% hit probability and uniform integer damage 1..4 on a
  hit. Damage is hardcoded in `primitive_transition`.
- Enemy initial HP by the six existing kinds is [8,10,12,16,12,10]. Current HP is
  visible on a fixed scale (HP/16); kind and sleep status are also visible.
- Enemy raw damage caps are [3,3,1,5,5,3], with uniform damage 1..cap after a hit
  and before existing defenses. Hit, block, and armour rules also affect the
  final damage. Enemy damage is currently inferable from fixed kind identity,
  but is not an explicit observation.
- There are 24 active ordinary enemies, despite capacity for 40 observation
  slots. The Python interface accepts other counts, but native reset asserts
  count==24 and placement loops use the fixed REQUIRED constant. Changing only
  the Python count is insufficient.
- HP-dependent REST availability, termination, regeneration clamps, and the
  per-turn update all need to use the same episode's stats.

## Observation expansion

Preserve the existing 1015 fields and append 83 scalar fields:

- Player current HP / 18, maximum HP / 18, and attack damage cap / 4.
- For each of the 40 existing encounter slots: enemy maximum HP / 16 and enemy
  raw damage cap / 5. Use the existing visible flag and slot assignment; both new
  fields must be zero whenever that enemy is outside current LOS or dead.

Keep the existing HP fraction and visible current-enemy-HP fields. Fixed scales
allow the same value to have the same meaning across episodes; values above one
are allowed. Do not divide by a changing training range or clip unseen strengths.
Record actual rounded integer stats, not just a difficulty label or multiplier.
Maximum HP distinguishes an injured tough enemy from a healthy weak enemy.

Do not expose total/remaining enemy count, offscreen enemies, or global enemy
stat multipliers. The model may know its own stats and the stats of currently
visible enemies. Exact visible damage is an intentional proxy affordance for
this experiment; inference of unknown monster capabilities is a separate task.

Zero-initialize the added first-layer columns and copy all old weights. Verify
that the expanded source reproduces the old source before training. Extend the
exact-D4 observation handling: the new scalar values remain attached to the
same enemy records and do not acquire a spatial direction. Rebuild nominal
replay observations with their actual stats, rather than zero-filled placeholders.

## First training distribution

Start with variation across episodes. Enemy HP and damage multipliers apply to
all six existing kinds within an episode; kinds retain their existing differences.

| Factor | Training levels | Original |
| --- | --- | --- |
| Player max HP | 12, 18, 24 | 18 |
| Player attack damage cap | 3, 4, 5 | 4 |
| Enemy initial/max HP multiplier | 0.75, 1, 1.25 | 1 |
| Enemy raw damage cap multiplier | 0.75, 1, 1.25 | 1 |
| Active enemy count | 12, 24, 36 | 24 |

Scale each kind's base value with `max(1, floor(base * multiplier + 0.5))`.
Publish the resulting vectors. Damage-cap rounding is substantial for weak
enemies: caps [3,3,1,5,5,3] become [2,2,1,4,4,2] or [4,4,1,6,6,4]. These
are raw caps, not equal percentage changes in expected post-armour damage.
Track realized damage and hit rates as diagnostics. Never count two multipliers
that round to identical full configurations as different generalization cases.

Hold regeneration fixed at its existing absolute rate, 0.23 HP per physical
turn, and keep accuracy, defenses, energy, and speeds unchanged. More maximum
HP therefore provides more reserve but also takes longer to restore from a
given fraction. This is a declared interaction; do not silently rescale healing.
Episodes begin at full HP. Low/half/full starting-HP probes belong in diagnostics.

The full grid has 243 configurations. Reserve 24 mixed configurations for
validation and 24 different mixed configurations for final test; train on 195.
Keep the nominal cell and all ten one-factor variations in training. Select and
freeze the reserved lists before running policies, balancing levels, enemy count,
and combinations of stronger/weaker player and enemies. Every individual level
and preferably every pair of levels must appear in training. Verify coverage
programmatically. No performance-driven reassignment of test cells is allowed.

Sample 25% nominal episodes and 75% uniformly over the other 194 training
configurations, independently of map identity. Retain the existing placement
mixture (one-third clumped training episodes); all first-pass counts are divisible
by six, so kind proportions and groups of three remain balanced. Evaluate ordinary
placements primarily and label any clumped diagnostic separately.

Use per-world episode parameters stored with state, not one batch-global Config.
Sample once at reset; preserve parameters through REST, snapshot restore,
checkpoint/resume, and death-state diagnostics. A frozen evaluation assignment
must survive autoreset without accidentally resampling a training configuration.

## Minimal first pass

Three policy comparisons, only two new training jobs:

1. Frozen expanded source: zero-shot behavior across all evaluation panels.
2. Fixed-stat PPO control: continue on the original nominal configuration.
3. Varied-stat PPO: continue on the training distribution above.

Use one seed and 5M PPO decisions for each trained arm, with checkpoints at
approximately 1M, 3M, and 5M (rounded to complete world steps). Start from the
same checkpoint with fresh optimizers. Match rollout/update settings and decision
budgets, and report physical turns, training seconds, and evaluation seconds.

For both new arms use ordinary episode resets, no new corrective labels, and no
death-state practice in this first screen. Keep nominal replay retention and the
navigation replay anchor equal across arms. Anchor replay contains real nominal
stats; do not apply an old-policy imitation loss to randomized-stat rollout
states, where changed actions may be appropriate. The new controls therefore
test ordinary continuation from the improved source, not a literal continuation
of the preceding supervised-practice trainer.

Do not reuse old verified action labels in altered-stat states: a retreat or
attack verified for the old damage/HP need not remain correct. If sparse-reward
PPO fails to learn the new conditions, a follow-up can collect fresh verified
examples within training configurations only. Treat that as a distinct intervention.

Select checkpoints using mean per-configuration exit rate, averaged across
sampled and greedy action modes, on a frozen validation panel: 16 representative
training configurations plus the 24 validation-only combinations. Use all 32
validation maps with two placements each: 2560 episodes per mode/checkpoint.
Include the frozen source as a candidate. Save the selection before final tests;
report nominal retention separately so an aggregate gain cannot hide its loss.

## Evaluation separates different kinds of generalization

Use the same evaluation seeds for all policies. Stat-only comparisons should
share map, player/stair/enemy placement, initial energy, and episode RNG seed.
Use separate RNG streams for parameter choice, placement, and game simulation.
Different actions can still consume randomness differently; these are paired
initial conditions, not identical subsequent random events.

For count comparisons, create a stable 40-position spawn deck and activate
prefixes. Reserve spawn cells away from the player and stairs so changing count
does not move them. This is a new experimental placement protocol; establish
baseline agreement and report the protocol rather than claiming exact old-seed
equivalence. Keep the old simulator and its result cohorts intact.

Main final panel: nominal + ten one-factor cells + eight representative seen
mixed cells + 24 test-only mixed cells = 43 configurations. Evaluate 100 held-out
test layouts x two placements each = 8600 episodes per mode per model. Also
evaluate the same configurations on a fixed subset of 32 training layouts with
new placements, clearly separated in reporting. This distinguishes:

| Stats | Layouts | Interpretation |
| --- | --- | --- |
| Seen configurations | Training layouts, new placements | In-distribution check |
| Seen configurations | Held-out layouts | Layout generalization |
| Held-out combinations | Training layouts, new placements | Stat composition |
| Held-out combinations | Held-out layouts | Both at once |

Report exit/death/timeout per configuration, mean and worst-quartile exit rate,
nominal retention, sampled/greedy results, turns to discovery/exit, REST turns,
and enemies alive at exit as a fraction of initial count. Use paired map-cluster
intervals for fixed panels. Do not treat thousands of repeated-map episodes as
independent layouts or a single training seed as replicated learning evidence.

Predeclare small additional test-only panels, reporting separately:

- Interpolation: player HP 15/21, counts 18/30, and enemy HP multiplier 0.875/1.125,
  one factor at a time. Check realized integer novelty. Integer player damage
  caps 3/4/5 have no unseen interior integer, so do not claim an interpolation
  test for that factor. Some enemy damage multipliers similarly alias old caps.
- Extrapolation: player HP 9/30, attack cap 2/6, enemy HP/damage multipliers
  0.5/1.5, counts 6/40, one factor at a time. The 40-enemy case also has slightly
  unequal kind proportions, which must be recorded. Do not start by stacking
  all adverse extremes and calling the result a generalization score.

## Does it actually use the stats?

Use a small fixed set of tactical probes after selection: corridor retreat,
mixed adjacent targets, and low-HP rest versus engagement. Hold geometry constant
and change one real stat at a time. Examine action probabilities and full-rollout
outcomes at low, half, and full starting HP. At equal player HP fraction, changing
maximum HP must now be distinguishable to the policy.

Verify action alternatives afresh under each stat setting and multiple future
RNGs before judging a choice. Stronger does not universally imply "attack" and
weaker does not universally imply "retreat"; geometry and the exit matter.
Cases with a verified change in preferred action are particularly informative.
Use training/validation probes for development and separate test probes for final
reporting. Do not use a weak deterministic controller to declare failure inevitable.

As a diagnostic only, replace appended stats with nominal values at evaluation,
while keeping game mechanics unchanged. A performance loss or changed decisions
shows sensitivity to these inputs, but misleading inputs are out of distribution
and are not a substitute for a separately trained feature ablation.

## Next extension: heterogeneous enemies on one floor

Only after the first screen, independently vary HP and damage for individual
enemies and randomize their assignment independently of kind/slot. Test, for
example, one tougher enemy among ordinary enemies, a high-HP/low-damage enemy
beside a low-HP/high-damage enemy, and mixed groups of three. Speed stays fixed
by existing kind. The policy sees each visible enemy's own stats.

First evaluate the episode-randomized policy on these mixed floors without
training there. Then train a separate arm with mixed enemies if needed. This
distinguishes transfer from learning the new distribution. Do not expose one
global difficulty code that allows the model to assume every enemy is alike.

## Required implementation checks and practical budget

- Replace fixed REQUIRED loops/assertions and every active-count dependency;
  inactive slots must have zero HP, no occupancy, and no actions/observations.
  Extend clump placement safely for non-multiples of three, or explicitly use
  ordinary placement in those later diagnostic cells.
- Keep player/enemy stats, maxima, REST termination, combat, and observations
  consistent. Snapshot compatibility requires a new schema/version.
- Check CPU/CUDA agreement at nominal settings and each axis extreme, D4
  covariance, unchanged initial policy outputs, and restored-state outcomes.
- Moving/changing an unseen enemy must not change the observation or legal-action
  mask; count and strength must not leak through normalization, slots, or padding.
- Verify actual spawn counts and per-kind proportions, stat rounding, independent
  randomization across maps/worlds, train/validation/test configuration disjointness,
  and held-out terrain separation. Stair success still does not require kills.
- Reuse existing terrain, distances, and LOS caches: none depend on these stats.
  No new maps or stat-specific LOS tables are needed.

The preceding run spent 218 seconds on 5M decisions with 512 worlds. Two 5M arms
would take about 7.3 minutes at that throughput, excluding evaluations; varied
counts and longer-lived episodes may change it. Benchmark the expanded simulator
before giving a wall-clock ETA. Limit the first pass to those two jobs; only
repeat promising results with additional training seeds or larger budgets.
Keep four compact checkpoints per arm plus one resumable checkpoint and bounded
aggregate diagnostics. Do not store every rollout. Retain existing disk guards.

## Execution

The experiment is isolated in this directory. `learn.cu` derives from the stairs
simulator and keeps its original counterpart unchanged. The expanded policy has
1098 inputs; the native output adds profile/count/stat and incoming-combat
diagnostics. The actual frozen split and rounded stats are in `profiles.json`.
Its 24 validation and 24 test combinations each contain exactly eight occurrences
of each level in every dimension; all pairwise level combinations exist in the
195 training configurations.

`preflight.py` passed 2688 paired CPU/CUDA decisions, semantic checks on 21
profiles, 1767 nonterminal decisions matching the old simulator from identical
saved states, unchanged source-policy outputs, all eight D4 transformations,
snapshot/RNG restoration, hidden-enemy observation checks, and terrain split
checks. The sampler covered all 195 training profiles in 4096 worlds, with
25.56% nominal episodes. Native compatibility is for identical states; initial
placement intentionally uses the new common spawn-deck protocol.

```sh
gpu-d1/.venv/bin/python -u gpu-d1/diagnostics/d1-stat-generalization/preflight.py
gpu-d1/.venv/bin/python -u gpu-d1/diagnostics/d1-stat-generalization/run.py
gpu-d1/.venv/bin/python -u gpu-d1/diagnostics/d1-stat-generalization/post.py
```

`post.py` may be launched while the main run is active; it waits for completion.
Before final test results, the evaluation plan was extended with 6400 nominal
episodes per model/action mode (seed 992301). The main panel's 200 nominal
episodes alone would give a weak retention estimate. This extra cohort does not
select checkpoints or change training.

Post-selection tactical probes use two valid geometry instances on test layouts
for each of corridor retreat, adjacent-target selection, and a sleeping monster
at distance seven. Each varies the four combat-stat factors one at a time plus
nominal stats, at low/half/full HP: 162 saved states. Enemy count is excluded
from these probes because the encounter intentionally contains only one to
three living enemies. Full-floor evaluations test quantity generalization.
The target-selection probe intentionally mixes a high-HP/low-damage enemy with
a low-HP/high-damage enemy; this mixture is not trained here.

Each legal first action is screened with 16 futures under the frozen source
continuation, and the selected action is compared with the source action on
64 independent paired futures. Every evaluated policy also runs its own full,
unforced greedy continuation on 64 fresh futures. Geometry validity, not policy
performance, selects the two instances per scenario type. Repeated futures and
stat settings do not turn these six geometries into 162 independent scenarios.

Generated libraries, checkpoints and state banks remain in ignored
`learning-runs/d1-stat-generalization/` under a 4 GiB storage cap. Main training
and post-processing have separate locks. The main manifest checks simulator,
trainer, source checkpoint, policy dependencies and compiled-library hashes.
Final tracked reports are `results/d1-stat-generalization.json` and
`results/d1-stat-generalization-probes.json`. No checkpoint is promoted by default.
