# Remembered walls: 11x11 ring and frontier-only ablations

## Correction: v1 results are not a valid wall-memory comparison

The tables below are historical v1 measurements, not evidence for the earlier
causal interpretation. The frontier-wall build allocated seven pointer inputs
but skipped the code filling them, leaving all seven zero. The ring also
distinguished unseen floor from unseen wall using hidden terrain and conflated
unknown wall with remembered floor. CPU/CUDA parity did not detect these shared
semantic errors. The earlier explanation of the frontier decline is withdrawn.

Revision 2 is prepared for fresh training. The 11x11 ring now encodes unknown
as 0, remembered wall as -1, and remembered floor as +1. Unknown cells have
the same value regardless of their hidden terrain. The frontier-only build
now fills its seven inputs and selects seen floor next to any unknown cell,
excluding remembered walls from unknown neighbors. Observation dimensions,
reward, task, and training settings are unchanged.

"Seen" means entering the 9x9 reveal square, which still reveals through walls.
Neither variant tracks footsteps or exposes a newly-revealed flag. A fresh
floor tile becomes remembered floor immediately and earns its one-time reward;
walls are remembered but earn no exploration reward. The frontier still uses
full-map shortest-path distances, and the base observation still exposes all
living enemies. These are corrected memory features, not fully realistic
partial observability.

Do not resume or evaluate v1 wall checkpoints with revision 2 observations.
Use new output directories ending in `walls-v2-100m-seed0` for fresh runs.
The semantic fixtures and CPU/CUDA parity checks passed before training with
`make -C gpu-d1 test-wall-observations`.

## Corrected v2 runs

Both corrected variants were trained from scratch for seed 0 to 100,007,936
decisions. The fresh evaluation uses 2,048 episodes and evaluation seed
`1200000`.

| variant | sampled clear | greedy clear | sampled kills | sampled timeout |
|:---|---:|---:|---:|---:|
| 11x11 ring, v2 | **50.10%** | **46.83%** | 7.16 | 49.07% |
| frontier pointer, v2 | **54.98%** | **47.41%** | 7.19 | 44.58% |

The corrected frontier pointer is active and learns normally. The corrected
ring is also active, but its v2 result is lower than the historical v1 ring
result because v2 removes the hidden distinction between unseen floor and
unseen wall. These are still one-seed results and retain the simulator's
full-map distance field for the frontier pointer.

Artifacts:

- `learning-runs/sleep-explore-ring-walls-v2-100m-seed0/`
- `results/sleep-explore-ring-walls-v2-100m-seed0-fresh-test.json`
- `learning-runs/sleep-explore-frontier-memory-walls-v2-100m-seed0/`
- `results/sleep-explore-frontier-memory-walls-v2-100m-seed0-fresh-test.json`

## Corrected v2 trajectory diagnostic

The final checkpoints were also run for 2,048 episodes with trajectory
instrumentation. Timeout episodes were characterized by search coverage, not
combat failure. In sampled rollouts, the ring timed out in 50.9% of episodes
and the frontier pointer in 46.6%. Those timeout episodes woke only 6.54 and
6.41 enemies on average, respectively, while clear episodes woke all eight.
Timeouts spent 84.7% and 84.4% of decisions moving, but only 15.1% and 14.8%
attacking. They visited 174 and 168 unique positions on average, and still
usually reached distance one from at least one remaining enemy. This is
consistent with incomplete map/enemy coverage and repeated travel between
targets, rather than a failure to win individual fights once an enemy is
found.

The diagnostic does not prove that the policy is literally revisiting the same
route inefficiently; it measures positions and target switches rather than an
optimal route distance. It does show that the next useful representation test
should expose or improve search coverage and frontier completion.

Trajectory artifacts:

- `results/sleep-explore-ring-walls-v2-trajectory-sampled.json`
- `results/sleep-explore-ring-walls-v2-trajectory-greedy.json`
- `results/sleep-explore-frontier-memory-walls-v2-trajectory-sampled.json`
- `results/sleep-explore-frontier-memory-walls-v2-trajectory-greedy.json`

## 512-decision deadline ablation

To test whether the corrected ring was primarily constrained by its episode
budget, the ring was retrained from scratch with the decision deadline doubled
from 256 to 512. The map, eight enemies, sleep rule, observation encoding,
reward, PPO settings, seed, and 100,007,936 training decisions were unchanged.
Only the per-episode deadline changed. The fresh evaluation again uses 2,048
episodes with evaluation seed `1200000`.

| variant | sampled clear | greedy clear | sampled kills | sampled timeout |
|:---|---:|---:|---:|---:|
| 11x11 ring, v2, 512-decision deadline | **96.63%** | **82.13%** | **7.92** | **2.59%** |
| frontier pointer, v2, 512-decision deadline | **97.85%** | **76.56%** | **7.95** | **1.71%** |
| ring plus frontier pointer, v2, 512-decision deadline | **97.07%** | **77.39%** | **7.92** | **2.05%** |

The matched trajectory diagnostic shows that sampled timeout episodes still
mostly reflect incomplete enemy coverage: they woke 6.37 enemies on average,
visited 203.5 unique positions, and spent 91.7% of decisions moving. Clear
episodes woke all eight enemies and visited 175.6 unique positions on average.
The greedy policy was weaker (80.76% clear in the diagnostic; 82.13% in the
independent report) and timed out after waking 5.84 enemies on average.

This is a large improvement over the 256-decision ring result (50.10%
sampled and 46.83% greedy clear). It indicates that the earlier ring policy
was strongly time-limited by search and enemy coverage. It does not show that
the policy found a more efficient search strategy: the longer deadline gives
it roughly twice as many opportunities to complete the same coverage task.

Artifacts:

- `learning-runs/sleep-explore-ring-walls-v2-512turn-100m-seed0/`
- `results/sleep-explore-ring-walls-v2-512turn-100m-seed0-fresh-test.json`
- `results/sleep-explore-ring-walls-v2-512turn-trajectory-sampled.json`
- `results/sleep-explore-ring-walls-v2-512turn-trajectory-greedy.json`
- `learning-runs/sleep-explore-frontier-memory-walls-v2-512turn-100m-seed0/`
- `results/sleep-explore-frontier-memory-walls-v2-512turn-100m-seed0-fresh-test.json`
- `results/sleep-explore-frontier-memory-walls-v2-512turn-trajectory-sampled.json`
- `results/sleep-explore-frontier-memory-walls-v2-512turn-trajectory-greedy.json`
- `learning-runs/sleep-explore-ring-memory-walls-v2-512turn-100m-seed0/`
- `results/sleep-explore-ring-memory-walls-v2-512turn-100m-seed0-fresh-test.json`
- `results/sleep-explore-ring-memory-walls-v2-512turn-trajectory-sampled.json`
- `results/sleep-explore-ring-memory-walls-v2-512turn-trajectory-greedy.json`

The 512-decision runs did not reach a clear hard plateau by 100M decisions.
Using the built-in 1,024-episode checks (evaluation seed `900000`), sampled
clear rates were:

| variant | 10M | 30M | 100M |
|:---|---:|---:|---:|
| ring | 85.55% | 93.85% | 96.88% |
| frontier pointer | 73.44% | 91.31% | 97.56% |
| ring plus frontier pointer | 71.58% | 92.48% | 98.05% |

Greedy performance also continued to rise: ring 28.91% → 73.83% → 83.69%,
frontier 27.54% → 56.93% → 75.20%, and combined 29.49% → 63.96% → 78.61%.
The gains are smaller late in training for sampled behavior, especially for
the ring, but one seed and three checkpoints are insufficient to call this a
true asymptote.

The combined observation has 253 values: the same 40-value remembered-wall
ring followed by the same 7-value frontier pointer. At 100M it sits between
the single-feature variants for sampled behavior (97.07%), while its greedy
result (77.39%) is slightly above frontier alone and below ring alone. The
extra information therefore does not produce a clear additive gain under the
same PPO budget; it appears to increase the representation and optimization
burden while providing a modest sampled-policy benefit over ring alone.

In the frontier trajectory diagnostic, sampled timeout episodes woke 6.26
enemies on average and spent 92.6% of decisions moving; greedy timeout episodes
woke 5.66 and spent 92.9% moving. This matches the ring diagnosis: residual
failures are primarily coverage and deadline failures, not inability to win a
fight once an enemy is reached.

The combined diagnostic has the same shape: sampled timeout episodes woke
6.39 enemies and spent 92.1% moving; greedy timeout episodes woke 5.68 and
spent 93.3% moving. Adding both memory summaries did not change the underlying
coverage bottleneck.

## Historical v1 setup and measurements (interpretation withdrawn)

These two runs keep the fixed native D1 map, eight enemies, six-tile sleep
rule, doubled first-seen reward, 256-decision deadline, PPO settings, and
seed-0 budget unchanged. The only memory addition is that every cell in the
9x9 view is recorded as viewed, including walls.

For the 11x11 ring, the existing 40 values now use `+1` for an unseen floor
cell, `-1` for a remembered wall, and `0` for seen floor or unknown wall. The
observation size remains 246. For the frontier-only run, a frontier anchor is
a seen floor cell adjacent to an unknown cell; remembered walls are removed
from the unknown frontier count. The pointer observation remains 213 values.

CPU and CUDA implementations matched exactly for both variants over 37 worlds
and 301 mixed actions.

## Fresh 2,048-episode evaluation

All rows use evaluation seed `1200000` and the same checkpoint budgets.

| feature | decisions | sampled clear | greedy clear | sampled kills | sampled timeout |
|:---|---:|---:|---:|---:|---:|
| 11x11 ring + wall marks | 10,027,008 | 25.59% | 25.29% | 6.62 | 73.10% |
| 11x11 ring + wall marks | 30,015,488 | 49.17% | 44.97% | 7.12 | 49.71% |
| 11x11 ring + wall marks | 100,007,936 | **61.38%** | **58.64%** | **7.34** | **37.70%** |
| frontier pointer + wall memory | 10,027,008 | 1.61% | 1.17% | 4.52 | 97.80% |
| frontier pointer + wall memory | 30,015,488 | 1.76% | 1.61% | 4.44 | 97.56% |
| frontier pointer + wall memory | 100,007,936 | 23.93% | 23.05% | 6.53 | 75.63% |

## Comparison with the corresponding no-wall versions

At 100M, the 11x11 ring rose from 57.67% sampled / 56.49% greedy clear to
61.38% / 58.64%. This is a modest improvement in both action modes. The
frontier pointer fell from 55.32% sampled / 49.22% greedy to 23.93% / 23.05%.

These numbers describe the flawed v1 implementations. They do not establish
that wall memory helps the ring or hurts the frontier pointer. Revision 2
requires fresh runs before drawing that comparison.

## Artifacts

- ring training run: `learning-runs/sleep-explore-ring-walls-v1-100m-seed0/`
- ring fresh evaluation: `results/sleep-explore-ring-walls-v1-100m-seed0-fresh-test.json`
- frontier training run: `learning-runs/sleep-explore-frontier-memory-walls-v1-100m-seed0/`
- frontier fresh evaluation: `results/sleep-explore-frontier-memory-walls-v1-100m-seed0-fresh-test.json`
- checkpoint comparison: `results/sleep-explore-wall-marking-checkpoints-fresh-test.json`
