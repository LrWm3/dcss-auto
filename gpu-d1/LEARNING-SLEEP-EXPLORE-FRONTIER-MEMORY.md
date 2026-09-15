# Sleep + doubled exploration reward + nearest-frontier memory

This run keeps the fixed native D1 map, eight enemies, six-tile sleep rule,
combat, 256-decision deadline, PPO settings, and doubled first-seen reward
unchanged. The policy receives seven additional values describing a compact
global memory target:

- the nearest previously seen floor cell that borders at least one unseen
  floor neighbor;
- that anchor's relative x/y position and shortest-path distance from the
  player;
- the number of unseen floor neighbors at the anchor; and
- the relative x/y direction of one such unseen neighbor.

The frontier-anchor set is maintained incrementally when the 9x9 view reveals
new cells, so observations do not scan the full 80x70 map. The resulting policy
has 213 inputs. CPU and CUDA implementations matched over 37 worlds and 301
mixed actions.

## Seed-0 fresh evaluation

Each row uses 2,048 episodes with evaluation seed `1200000`. Checkpoints were
evaluated independently with the same environment and seed.

| training decisions | sampled clear | sampled kills | greedy clear | greedy kills | sampled timeout |
|---:|---:|---:|---:|---:|---:|
| 10,027,008 | 21.78% | 6.39 | 16.46% | 5.43 | 77.44% |
| 30,015,488 | 36.28% | 6.74 | 28.96% | 6.05 | 62.89% |
| 100,007,936 | **55.32%** | **7.21** | **49.22%** | **6.79** | **44.19%** |

The signal produces a useful policy quickly, but its improvement mostly
levels out by 100M. The sampled policy still outperforms greedy by 6.10 points
at the final checkpoint, so stochastic action selection remains part of the
learned behavior.

## Comparison with the local frontier rings

The matched seed-0 results are:

| training decisions | feature | sampled clear | greedy clear |
|---:|:---|---:|---:|
| 10M | 11x11 ring | 19.87% | 16.06% |
| 10M | 12x12 ring | 17.77% | 12.26% |
| 10M | frontier memory | **21.78%** | **16.46%** |
| 30M | 11x11 ring | **36.33%** | **33.40%** |
| 30M | 12x12 ring | **37.55%** | 27.34% |
| 30M | frontier memory | 36.28% | 28.96% |
| 100M | 11x11 ring | **57.67%** | **56.49%** |
| 100M | 12x12 ring | 56.79% | 42.97% |
| 100M | frontier memory | 55.32% | 49.22% |

The nearest-frontier memory gives a small early advantage and avoids the severe
greedy degradation seen with the 12x12 ring, but it does not beat the 11x11
ring after 100M decisions. This suggests that naming a long-range frontier
anchor is useful, but the policy still lacks a reliable way to turn that anchor
into a multi-step route and then select among competing frontier branches.
The result is one seed, so it is evidence about representation rather than a
final ranking.

The full-information pursuit controller clears 99.76% on this suite. The
frontier pointer remains a local-memory aid, not a substitute for global
search or a route planner.

## Artifacts

- training run: `learning-runs/sleep-explore-frontier-memory-v1-100m-seed0/`
- final fresh evaluation: `results/sleep-explore-frontier-memory-v1-100m-seed0-fresh-test.json`
- checkpoint curve: `results/sleep-explore-frontier-memory-v1-checkpoints-fresh-test.json`
- build target: `make -C gpu-d1 build/learn_sleep_explore_frontier_memory.so`
