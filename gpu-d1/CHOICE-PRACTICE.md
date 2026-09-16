# Target selection and safe pre-combat recovery

Nine jobs: three seeds, each branched from its existing 30M exact-D4/clumped model
into an unchanged control, target-selection curriculum, or sleep/recovery
curriculum. Train each to 60M total (30M additional decisions), with snapshots
and evaluations at 40M, 50M, and 60M. The two curricula are separate; they are not
combined with each other or the previous hallway/pocket curriculum.

The starting model is the highest ordinary-floor clear-rate configuration from
the preceding screen. All three branches preserve its optimizer, model, RNG,
worlds, and counters. Ordinary training remains 24 enemies, 2048 turns, one-third
clumped placement, 15x15 wall-blocked vision, LOS wake, seen-tile input, and the
existing rewards (+1 kill, +3 clear, -4 death, +0.002 new floor, -0.001 turn).
No new action, demonstration, tactical reward, or observation channel is supplied.

## Target selection

Two awake enemies are adjacent at the start: kind 0 (damage 3) and kind 3
(damage 5). Positions, room size, rotations/reflections, player HP, and enemy HP
vary. Their discovery-record order is randomized independently of side/type;
both are already visible, so this represents different remembered discovery
histories and reveals no hidden information. The policy may attack, move, or wait.

Training player HP is 2/4/6; held-out player HP is 3/5/7. Enemy-HP profiles include
equal HP, a nearly dead weaker enemy, and a wounded dangerous enemy. Training
weak/strong HP pairs are (6,6), (1,16), (8,1), (8,8). Held-out pairs are (7,7),
(2,15), (7,2), (7,7). Duplicate equal-HP profiles intentionally provide half the
starts; the other two profiles each provide one quarter.

The scripted controls focus the weaker enemy, focus the dangerous enemy, or
choose the lowest-HP adjacent enemy. They do not retreat. Their outcomes establish
that target choice can matter and that one fixed type priority is insufficient;
they are not optimal-policy proofs. Model evaluation also reports first-action
probabilities by HP profile. Improved survival through repositioning is valid,
but is not by itself evidence of better target selection.

## Sleeping enemy and recovery

One enemy is visible seven tiles away, outside the native six-tile wake radius.
Waiting in place keeps it asleep and uses the existing regeneration mechanic.
Approaching wakes it normally. There is no explicit sleep-status input: the model
sees the same position, type, HP, player HP, and other features as before.

An ordinary single monster was too forgiving for this question. The scenario
uses the ordinary kind-3 combat/speed rules but increases its HP to 32 in training
and 28 in held-out tests. Its HP is exposed normally (the HP feature is not clipped).
No attack damage, energy, defenses, regeneration, wake rules, or combat code change.
This is deliberately a tougher HP proxy, not an ordinary D1 encounter.

Three quarters of starts have low player HP: 1/3 in training, 2/4 held out.
One quarter start at full HP (18), where waiting provides no healing benefit.
The controls either approach immediately or wait until full HP and then approach;
once adjacent, both attack. No script is used during training. Because combat is
stochastic, the intended contrast is a large survival-probability advantage, not
a guarantee that every immediate attack dies and every delayed one survives.

Evaluation reports low/full-HP outcomes separately, waiting while the monster is
asleep, HP when wake-up is first observed, actions, clears, deaths, and unresolved
episodes. Unnecessary full-health waiting and increased waiting in unrelated
combat are important possible regressions.

## Distribution and evaluation

Each curriculum replaces 10% of episode selections with its custom scenario.
This is not 10% of decisions; actual decisions/episodes/outcomes are counted.
Live ordinary worlds finish their current episode before curriculum selection.
The ordinary world pauses while its paired custom world advances. Each scenario
has only one or two required enemies remaining, so reaching the standard clear
reward is much more frequent than on full floors. This is part of the intervention.

Each task has 16 training and 16 held-out layouts, including all eight orientations.
Training and held-out floor hashes are disjoint; held-out rooms have different
widths. This is generalization within these scenario families, not a claim of
arbitrary tactical competence. Diagnostic outcomes use 4,096 episodes per task
per checkpoint, fixed seeds, and a 512-action cap separate from the native 2048-turn
limit. Ordinary validation uses the existing 32 maps and 1,024 episodes. Ordinary
test maps remain untouched.

At 60M each model also runs the earlier frozen combat-state and held-out tactical
suite, to detect regression in pocket defense or an indiscriminate increase in
waiting. Three training seeds are the independent replication units; thousands of
combat trials are not thousands of independent training runs.

## Implementation and launch

Branch: `branches/vision15-choice-practice-v1`. Its native file includes the
unchanged versioned simulator from `vision15-tactical-next-v1`; the added CUDA
code only initializes scenarios and supplies diagnostic controllers/state probes.
Generated maps, libraries, live checkpoints, and logs remain ignored under
`learning-runs/choice-practice-assets` and `learning-runs/vision15-choice-practice`.
Existing ignore rules cover these outputs.

Using `.venv/bin/python`, run `scenarios.py`, `assets.py`, then
`evaluate.py --controls --output results/choice-practice-controls.json`,
`preflight.py`, and `run_experiment.py`. The last script runs the persistent
sequential queue, with 3 GiB checkpoint budget and 10 GiB free-space reserve.
The preflight checks safe sleep/regeneration, visibility, mixed-world episode
switching and exact resume, and real PPO updates/checkpoint resume for each arm.

Results: `results/choice-practice-*.json`. Training time is recorded separately
from evaluation and includes only additional work when reported as added time.
