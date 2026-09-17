# D1 stat and quantity generalization experiment

Status: complete, 2026-09-17. The design below was committed
before implementation. Execution details and results are appended at the end.

Follow-up: [isolated enemy danger, healing, and escape](SINGLE-ENEMY.md)
confirms avoidable single-enemy deaths and tests whether the policies retreat.

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

## Completed results

Both arms completed 5,000,192 PPO decisions, seed 0. Validation selected the
3,000,320-decision checkpoint for each. Fixed-stat PPO used 293.0 training seconds
and 6,068,704 physical turns; varied-stat PPO used 292.0 seconds and 6,009,513
physical turns. The main pipeline took 852.4 seconds (14.2 minutes), with nominal
retention and tactical checks adding roughly another 1.6 minutes. Tactical
collection, action verification and three-policy evaluation took 30.6 seconds.

### Full floors

Success means descending alive, not killing every enemy. Held-out combinations
below use 24 previously excluded configurations x 100 test layouts x two placements
= 4800 episodes per policy/action mode. The larger nominal check uses 6400 episodes.

| Evaluation | Frozen source | Fixed-stat PPO | Varied-stat PPO |
| --- | --- | --- | --- |
| All 43 main configurations, sampled | 96.62% | 97.03% | 97.02% |
| All 43 main configurations, greedy | 96.08% | 96.41% | 96.35% |
| Held-out combinations, sampled | 95.77% | 96.06% | 96.13% |
| Held-out combinations, greedy | 95.40% | 95.81% | 95.48% |
| Nominal retention, sampled | 98.11% | 98.83% | 98.75% |
| Nominal retention, greedy | 97.56% | 97.80% | 97.70% |
| Interpolation, sampled | 98.25% | 98.42% | 98.92% |
| Interpolation, greedy | 96.75% | 96.67% | 97.67% |
| Extrapolation, sampled | 95.60% | 95.50% | 96.20% |
| Extrapolation, greedy | 94.35% | 94.50% | 95.45% |

There is no established main-panel advantage for varied training over the matched
control. On held-out combinations its sampled advantage is +0.0625 percentage
points, paired map-cluster 95% interval [-0.542, +0.667]; greedy difference is
-0.333 points [-0.938, +0.250]. Across all 43 configurations the differences are
-0.012 sampled [-0.442, +0.407] and -0.058 greedy [-0.535, +0.453].

The 6400-episode nominal check has 121/75/80 sampled deaths for source/fixed/varied,
respectively, and no sampled timeouts. Varied's gain over the source is +0.641
points [+0.297, +0.984], but its difference from fixed continuation is -0.078
[-0.438, +0.250]. The ordinary capability survives this expansion; extra stat
variation is not needed to explain the nominal improvement.

Interpolation and extrapolation have favorable varied-training point estimates.
Their greedy gains over the frozen source are +0.917 and +1.100 points, with
intervals [+0.083,+2.000] and [+0.150,+2.200]. Against the fixed-stat control the
intervals touch or include zero: [0.000,+2.167] and [-0.050,+2.100]. These are small
exploratory panels among several comparisons, not independent confirmation that
varied training is superior. No multiple-comparison adjustment was applied.

On the 32 training-layout evaluation subset with fresh placements, varied PPO
is worse than fixed PPO in sampled main-panel exits: 94.95% versus 96.04%, delta
-1.09 points [-2.11,-0.18]. Greedy results are close (94.19% versus 94.00%). This
regression also argues against claiming a consistent overall benefit.

The range was not uniformly trivial: one validation combination (12 player HP,
1..3 player damage, nominal enemy HP, 1.25x enemy damage, 36 enemies) gave the
source only 41/64 sampled exits, versus 63/64 for nominal stats. However, a high
average success rate leaves relatively little failure signal in ordinary PPO.

### Tactical and observation interventions

| Scenario family, full greedy continuations | Frozen source | Fixed-stat PPO | Varied-stat PPO |
| --- | --- | --- | --- |
| Corridor, 54 stat/HP/geometry states x 64 futures | 90.19% | 88.54% | 90.22% |
| Adjacent target selection, same sweep size | 96.88% | 96.88% | 96.88% |
| Sleeping enemy/rest, same sweep size | 100% | 100% | 100% |

Replacing the appended inputs with nominal values changes the varied model's
initial greedy action on only 1/162 states. Its average action-distribution total
variation is 0.00446; the fixed-stat control is 0.00115 and the expanded frozen
source is exactly zero. Across 36 paired player-damage-only comparisons, the
varied model changes no greedy first action; mean total variation is 0.00157.
These are weak responses, not proof that the new fields are entirely unused.

On full floors, accurate rather than nominalized appended stats improves varied
PPO exits by +0.105 sampled points [-0.233,+0.442] and +0.174 greedy points
[-0.047,+0.407]. Neither interval excludes zero. This intervention supplies
misleading inputs and is not equivalent to training without stats.

Fresh verification finds eight corridor states where another first action is
at least 20 points better and exits at least half the time. All are missed by
both trained policies. For example, at 3/12 HP in map seed 72852, source ATTACK NW
exits in 19/64 confirmation futures, while MOVE E followed by the unchanged source
exits in 40/64. Both trained models still choose ATTACK NW. At nominal 5/18 HP in
the same geometry, confirmation is 35/64 versus 54/64; again neither changes.
These are two variants of one geometry, not independent discovered mechanisms.

Target-selection and rest probes are largely solved already. Low/half-HP rest
cases all select REST for all three policies, and all target-selection states
select ATTACK E against the fragile, high-damage target. These probes do not
establish learning a new stat-dependent tactical rule. The one greedy flip caused
by restoring accurate stats is not one of the eight verified corrections.

### Interpretation

The existing policy is reasonably robust to these stat and density changes,
including previously unseen combinations and moderate out-of-range values.
This first 5M-decision screen does not establish that varied-stat PPO improves
over ordinary continuation or learns useful new power-sensitive tactics. There
are favorable secondary trends, but the main comparisons are inconclusive and
the new inputs have little behavioral influence in the controlled probes.

Robust survival must not be equated with understanding power: a conservative
policy can work across several strengths without changing its decisions. The
next informative diagnostic would verify situations where changing actual power
reverses which action is better, then test whether the policy follows that
reversal. The current target/rest probes often have the same sensible choice
throughout the sweep. This run provides neither evidence that such learning is
impossible nor a reason to promote the varied checkpoint over the control.

All confidence intervals describe paired map variation for one training seed.
The test layouts are disjoint from training but reused from earlier studies.
