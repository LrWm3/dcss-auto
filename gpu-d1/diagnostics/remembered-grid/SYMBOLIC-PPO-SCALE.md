# Durability and full-size progression

## Decision made before results

Run the corrected configuration (detached critic, complete discounted returns,
all navigation parameters actor-trainable) from the original imitation source
to 3M active decisions for training seeds 0 and 1. Retain 100k, 500k, 1M and 3M
checkpoints. The prior 500k checkpoint lacked RNG state, so seed 0 starts again;
CUDA kernels are not forced deterministic, and same-seed runs need not reproduce
identical trajectories. New checkpoints save RNG, optimizer, scaler and counters
for future continuation.

The prespecified engineering gate requires **both seeds** at 3M to:

- Keep each known-stair/exploration score within 5 percentage points of source
  on main greedy, long greedy, and main sampled evaluation.
- Retain >=95% threat-backtracking success on those evaluations.
- Gain >=5 percentage points on long greedy known-stair navigation.

These are practical screens, not statistical significance tests. The output is
`results/symbolic-ppo-durability-gate.json`. Failure prevents automatic full-size
training and triggers troubleshooting rather than relaxing thresholds.

## Full-size setup, conditional on passing

Use actual 80x70 geometry from the existing disjoint native D1 corpus splits:
64 train, 16 validation, 32 test layouts, chosen with fixed independent seeds.
Each layout has four start/goal pairs and two knowledge conditions: stairs known
through a real traversed history, or unexplored start. Goal distance is 24–128
steps, and three nearby stair tiles are usable exits. There are **no enemies**
in this navigation-only stage; these are not full-game Crawl episodes.

The 15x15 local crop and 16x16 coarse global representation stay fixed. Native
observations expand to 70x80. History, walls, visitation, stairs, LOS and action
semantics remain unchanged. Precomputed distances construct fixture histories;
they are not policy observations. Actual LOS tables come from the existing
compiled native corpus. Geometry hashes are checked disjoint across splits.

Full-size training is seeded from the **seed-0 3M** checkpoint, chosen in advance
rather than selected by test scores. Run 1M additional active decisions, seed 0,
1024 physical turns, evaluating before training and at 100k/500k/1M. This changes
both geometry distribution and deadline, so the baseline and fine-tuned policy
are compared on the same full-size scenarios/deadline.

Before that run, execute the existing small-map CPU/GPU semantic preflight and
new full-size CPU/GPU parity checks. Full-size deterministic-controller
validation must achieve >=95% known-goal and >=90% exploration success, to catch
invalid geometry/history or an obviously inadequate deadline before PPO.

Prepared fixtures are compressed and stored under ignored training outputs;
no duplicate raw corpus is committed. Sources/hashes are recorded in their
manifest. Only bounded checkpoints and JSON summaries are persisted.

## Commands and artifacts

Use the compiler-header CPATH documented in EXECUTION-OPTIMIZATION.md.

```sh
python symbolic_ppo_scale_suite.py
python symbolic_fullsize_stage.py
```

The full-size stage waits for the two-seed gate and exits without training if
it fails. The scripts refuse existing checkpoint outputs. Logs/checkpoints are
under `learning-runs/remembered-grid/symbolic-ppo-durable-seed{0,1}` and
`symbolic-ppo-fullsize-seed0`; reports use the same names under `results/`.

`fullsize_navigation.py` prepares maps and a separately compiled native library;
`check_fullsize_navigation.py` checks geometry, observation semantics, transitions,
and the deterministic controller. The default 32x32 library/interface remains
available and is regression-tested before full-size progression.

## Completed durability results

Both seeds passed every prespecified gate at 3M. Greedy held-out success (%):

| Checkpoint | Main known | Main explore | Long known | Long explore |
|---|---:|---:|---:|---:|
| Imitation source | 91.80 | 94.53 | 77.34 | 81.25 |
| Seed 0, 1M | 96.48 | 93.75 | 95.31 | 81.25 |
| Seed 0, 3M | 96.09 | 93.75 | 92.97 | 82.03 |
| Seed 1, 1M | 96.09 | 92.97 | 91.41 | 82.81 |
| Seed 1, 3M | 96.88 | 93.75 | 87.50 | 85.16 |

Threat-backtracking remained 100% in every final evaluation. Main sampled
known-stair success rose from 82.42% to 96.09% / 97.66% for seeds 0 / 1; sampled
exploration rose from 92.58% to 94.14% / 95.70%.

Each 3M run took approximately 400.6–400.8 seconds of collection plus updates,
about 7,495 active decisions/s; setup and checkpoint evaluations are excluded.
No AMP overflow skips occurred. Main navigation scores have 256 episodes per
condition, long scores 128, and threat scores 32. The same fixed held-out cases
are reused across checkpoints; this is a durability/generalization screen, not
a claim of significance or independent test selection. Seed 0 improved long
known navigation more than seed 1, so learning trajectories still vary.

The full-size preflight passed 1,247 CPU/CUDA transition comparisons across
eight scenarios on eight different native layouts and checked 112 distinct layout hashes. Deterministic validation
was 64/64 known-stair and 64/64 exploration successes, averaging 41.34 and 181.09
additional turns respectively, under the 1,024-turn deadline.

## Full-size PPO results

Native held-out test success (%), 128 episodes per condition:

| Checkpoint | Greedy known | Greedy explore | Sampled known | Sampled explore |
|---|---:|---:|---:|---:|
| Transferred seed-0 3M source | 7.03 | 25.78 | 29.69 | 39.84 |
| 184,933 additional decisions | 10.94 | 22.66 | 26.56 | 35.94 |
| 543,138 additional decisions | 8.59 | 22.66 | 23.44 | 42.97 |
| 1,046,192 additional decisions | 10.94 | 22.66 | 25.78 | 46.09 |

Training took 134.79 seconds for 1,046,192 active decisions (7762/s),
excluding setup and evaluations. Memory use observed during training was about
9 GB. No overflow skips occurred. Rollout/replay log-probability differences
stayed below the 0.03 assertion threshold. The 100k and 500k checkpoints occur
after whole episode batches, so actual counts overshoot those targets.

This is **not a successful full-size transfer**. All failures are timeouts, and
greedy policies reverse direction hundreds of times per episode. Final known
validation success is 9.38%, exploration 37.50%; the deterministic controller
reaches 100% for both on that same validation set. The increase in sampled
exploration does not establish improved known-goal navigation.

The native run contains only 12 complete episode batches (1,536 episodes),
versus 461–466 batches in each small-map 3M run. Decision counts therefore do
not match the number of distinct episodic learning opportunities. The corpus,
geometry, global aggregation scale and deadline also change together.

## Transfer troubleshooting

`symbolic_fullsize_diagnostic.py` checks optimized symbolic preprocessing against
the independent reference on native observations, then runs matched greedy
rollouts. Local crops and global fractional channels passed exact comparisons;
terrain fractions sum to one. Normal diagnostic evaluations reproduce exit
rates from the training report. Minor floating-point trajectory differences
change a few reversal counts without changing these success rates.

| Task / intervention | Known success | Exploration success |
|---|---:|---:|
| Small, transferred source unchanged | 96.09% | 93.75% |
| Small, only global map padded to 80x70 | 72.66% | 84.77% |
| Small, global encoded feature erased | 96.88% | 92.19% |
| Native, source unchanged | 7.03% | 25.78% |
| Native, source global feature erased | 10.16% | 20.31% |
| Native, after 1M unchanged | 10.94% | 22.66% |
| Native, after 1M global feature erased | 8.59% | 22.66% |

The padded-global intervention leaves small-map dynamics, local/tactical input,
action masks, history and deadline unchanged. It changes global binning, player
bin placement, and unknown padding together. This causally establishes a
global-representation distribution-shift effect, not which of those components
is responsible. It does not isolate the sole cause of the native-layout gap.

Erasure preserves most small-map navigation, but threat success falls from
100% to 90.625% (three deaths), so the global branch is not wholly unused or
safe to discard. On native geometry, erasure fails to recover performance.
The remaining gap could involve unfamiliar local geometry, long routes and
insufficient global planning; these experiments do not separate those causes.

Conclusion: the update correction passes the two-seed durability screen. Native
navigation does not pass a competence screen after 1M PPO decisions. Do not
interpret the faster full-size pipeline or modest sampled-exploration gain as
solved map generalization. A sensible next experiment is native-scale training
with easier short routes and demonstrator coverage before extending route
length, while keeping the same 15x15 local crop and no runtime route hints.

All runs and diagnostics finished. Checkpoints/maps remain in ignored local
outputs; source and bounded JSON reports are versioned.
