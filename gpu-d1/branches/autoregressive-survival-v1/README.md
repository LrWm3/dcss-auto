# Survival tactics practice: anchored autoregressive PPO

Three seed-0 continuations start from the identical 30,000,128-decision
navigation-only-anchor checkpoint, preserving model, optimizer, ordinary live
worlds, RNG state and the fixed original imitation reference. Each adds 5M
policy decisions, with checks after approximately 500k, 1M and 5M. The separate
smoke test is discarded; its updates are not used by any experimental arm.

| Arm | Ordinary decisions | Tactical decisions | Practice sampling temperature |
|---|---:|---:|---:|
| Control | 100% | 0% | 1 |
| Practice | 90.04% | 9.96% | 1 |
| Practice + exploration | 90.04% | 9.96% | 5 |

The practice arms allocate 51 of 512 worlds to tactical episodes. This is a
fixed decision allocation, not 10% of episodes: short encounters would otherwise
occupy very few training transitions. Ordinary native worlds assigned to
practice are parked rather than overwritten, and all state is checkpointed.
Because practice episodes are shorter, they contribute more episode endings
per decision. The actor/critic losses retain ordinary per-transition weighting.

All layers train. No actions are forced or demonstrated during training.
Rewards stay +1 for clearing, -0.00001 per physical turn, and zero for kills,
exploration and death. Clearing still requires defeating all living enemies.
There is no reward or policy input for retreating or reaching a designated goal.
All other settings retain the 30M configuration: 24-enemy ordinary floors,
2,048 physical turns, wall-blocked vision and wake checks, visible sleep status,
individual MOVE/ATTACK/WAIT and REST macro, D4-averaged policy, gamma 1,
GAE lambda .95, entropy coefficient 0, PPO learning rate .0003.
The fixed imitation policy is anchored only when no awake enemy is visible.

## Encounters and split

Four families, each with two training geometry variants, two different held-out
variants, and all eight rotations/reflections: 64 train and 64 held-out layouts.
Geometries have no identical floor layouts across splits.

- Hallway: retreat from several adjacent enemies into a narrow passage.
- Diagonal pocket: reach protected cover at an angle, with distances varied.
- Passing enemy: a nearby foe obstructs the direct approach to off-axis cover.
- Separated groups: two groups approach around a wall, with a narrow retreat.

Initial HP is 6, 12 or 18. Eighty percent of episodes contain six awake enemies,
with mostly tougher kinds; the remainder have one weak foe to include situations
where retreat has little benefit. Enemy energy phase varies. All local terrain
is remembered (a previously explored room), but current LOS and visible enemy
knowledge remain native. Unknown disconnected padding exists only for the
simulator's terminal reset. Goal, family and split labels live solely in the
fixture metadata and diagnostics, never in the 999 policy inputs. The goal is
one designated cover tile for measurement; reaching it is not required to win.

The cover controller used to check difficulty knows the designated destination
and map paths. It moves along legal unoccupied descending-distance steps, then
attacks adjacent enemies or waits. It is a diagnostic comparator, not an optimal
oracle, and provides no training labels. Held-out clear rates before training:

| Family | Original deterministic controller | Cover-first diagnostic controller |
|---|---:|---:|
| Hallway | 37.5% | 88.3% |
| Diagonal pocket | 39.1% | 85.9% |
| Passing enemy | 33.6% | 85.9% |
| Separated groups | 42.2% | 89.1% |

## Exploration and evaluation

The exploration arm divides both action-type logits and conditional-direction
logits by 5 only for practice decisions. Both rollout log probabilities and PPO
update log probabilities use the recorded per-transition temperature. There are
no unaccounted action overrides. Values, ordinary training, imitation anchoring,
and all evaluation use the original model semantics. Temperature is not a model
input. Entropy regularization remains zero.

A 512-state calibration on the training fixtures put mean MOVE probability in
multi-enemy starts at 0.000193% for temperature 1, 1.01% for temperature 3,
and 5.33% for temperature 5. Temperature 5 was selected from these initial-state
training measurements, before outcome comparisons. Any MOVE is not necessarily
a useful retreat; this tests whether broader experience enables learning one.

Every checkpoint evaluates ordinary validation (32 maps x 32 placements) and
held-out tactics (64 layouts x 8 combat seeds), sampled and greedy, temperature 1.
Tactical metrics include clears, deaths, timeouts, designated cover reached,
turns with multiple adjacent enemies, waiting during adjacency, and first MOVE
probability. Metrics are split by family and one/multiple starting enemies.
Initial baseline and controller evaluations use the same held-out scenarios.
One training seed per arm is an exploratory screen, not a multi-seed conclusion.

## Checks and operation

Preflight checks passed: bitwise original/default-policy output parity,
unit-temperature parity, exact joint-action log probabilities, an unchanged
policy's PPO ratio of one under mixed temperatures and minibatch permutation,
finite gradients, inactive-world preservation, exact mixed-state step replay,
and an unchanged fixed original imitation reference. Native action legality,
reward accounting and termination are asserted during held-out evaluations.
An 8,192-decision smoke continuation, including PPO and both evaluation suites,
completed successfully in 18.7 seconds. The original simulator source is copied
unchanged into this isolated branch; only fixture initialization is new.

Run from repository root with `gpu-d1/.venv/bin/python`:

1. `gpu-d1/branches/autoregressive-survival-v1/scripts/scenarios.py`
2. `gpu-d1/branches/autoregressive-survival-v1/scripts/preflight.py`
3. `gpu-d1/branches/autoregressive-survival-v1/scripts/run_experiment.py`

Progress/checkpoints: `gpu-d1/learning-runs/autoregressive-survival/`.
Results: `gpu-d1/results/autoregressive-survival.json`.
Initial checks: `gpu-d1/results/autoregressive-survival-preflight.json`.
Manifests hash sources, source checkpoint, maps and native library. Sequential
jobs are resumable; storage has a 4 GiB run cap and 10 GiB free-space reserve.
Generated assets are about 136 MiB and use existing ignore rules. Only milestone
snapshots plus latest/best checkpoints are retained. Training seconds and total
pipeline time are reported separately.

## Completed 5M results

All three arms finished at 35,000,320 cumulative decisions (5,000,192 additional
per arm). Total additional training was 480.6 seconds; the full queue including
nine checkpoints' evaluations took 708.3 seconds (11.8 minutes).

The practice-plus-exploration arm learned a large improvement on held-out
encounters, evaluated at normal temperature with no forced actions. Practice
alone helped considerably less, and ordinary training alone regressed on these
constructed encounters despite retaining ordinary-floor performance.

| Arm | Tactical sampled clear | Tactical greedy clear | Ordinary sampled clear | Ordinary greedy clear |
|---|---:|---:|---:|---:|
| Starting 30M checkpoint | 29.69% | 33.59% | 96.39% | 94.82% |
| Ordinary continuation | 24.22% | 23.44% | 96.00% | 94.43% |
| Practice | 37.30% | 38.48% | 96.09% | 93.75% |
| Practice + exploration | **79.88%** | **80.86%** | **96.09%** | **94.34%** |

Tactical evaluation uses 512 episodes, ordinary evaluation 1,024. The original
deterministic teacher scores 38.09% on these tactical cases; the cover-first
diagnostic controller scores 87.30%. Thus the strongest arm exceeds both its
neural initialization and the original teacher on this constructed held-out
problem distribution. This does not establish a gain on ordinary floors.

Practice-plus-exploration tactical clears continued improving:

| Additional decisions | Sampled | Greedy |
|---|---:|---:|
| 500k | 53.91% | 51.37% |
| 1M | 59.38% | 55.86% |
| 5M | 79.88% | 80.86% |

At 1M, ordinary sampled/greedy clears dipped to 93.07%/92.29%, then recovered
to the final values above. The final ordinary greedy score is one clear below
the control out of 1,024 episodes; sampled is one clear above. This is reassuring
for retention, not proof of statistical equivalence or no possible regression.

Final greedy tactical clears by family:

| Family | Ordinary continuation | Practice | Practice + exploration |
|---|---:|---:|---:|
| Hallway | 28.91% | 39.84% | **85.16%** |
| Diagonal pocket | 21.09% | 36.72% | **65.63%** |
| Passing enemy | 17.97% | 33.59% | **82.81%** |
| Separated groups | 25.78% | 43.75% | **89.84%** |

The effect is not explained by succeeding only on the easy cases. On the 404
multi-enemy episodes, greedy clears increase from 15.84% at initialization to
75.74% with practice plus exploration. On 108 single-enemy episodes the final
policy clears 100%.

Behavioral diagnostics are consistent with learning useful positioning:
- Initial MOVE probability on held-out starts rises from 7.18% to 90.80%.
- Mean turns with multiple adjacent enemies fall from 9.67 to 3.55 in greedy
  evaluation, despite mean encounter duration increasing from 12.55 to 31.08.
- Reaching the designated cover tile rises from 0% to 25.20%.
- WAIT with an adjacent enemy falls from 30.85% of such decisions to zero.

These aggregate metrics do not establish exactly which routes or strategies
were learned. Designated cover is one endpoint, not every potentially useful
position; the agent can survive without reaching it. The diagonal-pocket family
remains noticeably weaker than the other three. Detailed trajectories and older
independent probes would help establish the breadth of tactical transfer.

Each practice arm collected 498,066 tactical decisions and 4,502,126 ordinary
decisions. Practice alone completed 41,089 tactical episodes; exploration
completed 19,873. Longer encounters and differing behavior therefore change the
number of training episodes despite matched total and tactical decision counts.
There was no survival/cover shaping reward and no new demonstration training.

The sampled clear gain over initialization is +50.20 percentage points; greedy
is +47.27 points. A paired bootstrap that clusters all eight orientations and
all combat seeds of each of the eight base geometries gives respective 95%
intervals of +40.82 to +56.64 and +36.52 to +55.66 points (10,000 draws, seed 713).
These intervals describe the selected geometry panel, not variation across
training seeds or arbitrary Crawl encounters. This is one training seed, four
hand-designed families, and fully remembered local terrain. Replication and
broader transfer evaluation remain necessary.

Completed results: `gpu-d1/results/autoregressive-survival.json`.
Paired comparisons: `gpu-d1/results/autoregressive-survival-comparison.json`.
No jobs remain running or queued in this experiment.
