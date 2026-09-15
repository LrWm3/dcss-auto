# Sleep + doubled exploration reward + 12x12 frontier ring

This is the same toy task as the 11x11 frontier-ring experiment: the fixed
native D1 map, eight enemies, six-tile sleep rule, combat, 256-decision
deadline, PPO settings, and seed-0 training run are unchanged. The reward is
`+0.002` for each newly revealed floor cell in the 9x9 reward view.

The only task-facing change is the observation. In addition to the original
206 inputs, the policy receives a corner-trimmed outer perimeter of a 12x12
player-centered window: 44 binary values. A value is one when that cell is
floor and has not yet entered the 9x9 reward view; walls and already-seen
floor are zero. The policy therefore has 250 inputs. The CPU and CUDA
implementations matched over 37 worlds and 301 mixed actions.

## Seed-0 fresh evaluation

Each row uses 2,048 episodes with evaluation seed `1200000`. Checkpoints were
evaluated independently with the same environment and seed.

| training decisions | sampled clear | sampled kills | greedy clear | greedy kills | sampled timeout |
|---:|---:|---:|---:|---:|---:|
| 10,027,008 | 17.77% | 6.33 | 12.26% | 5.07 | 80.42% |
| 30,015,488 | 37.55% | 6.93 | 27.34% | 6.07 | 61.18% |
| 100,007,936 | **56.79%** | **7.23** | **42.97%** | **6.49** | **42.58%** |

The policy continues to learn through 100M decisions: sampled clear rate rises
39.0 percentage points from 10M and the sampled timeout rate falls 37.8
points. The gap between sampled and greedy behavior remains substantial at
100M, so the learned action distribution still contains useful exploration
that argmax removes.

## Comparison with the 11x11 ring

The 11x11 reference used the same fixed task, reward, evaluation suite, and
training budget. The matched seed-0 results are:

| training decisions | ring | sampled clear | greedy clear |
|---:|:---:|---:|---:|
| 10M | 11x11 | 19.87% | 16.06% |
| 10M | 12x12 | 17.77% | 12.26% |
| 30M | 11x11 | 36.33% | 33.40% |
| 30M | 12x12 | **37.55%** | 27.34% |
| 100M | 11x11 | **57.67%** | **56.49%** |
| 100M | 12x12 | 56.79% | 42.97% |

The larger ring does not provide a reliable improvement. It is slightly ahead
of 11x11 in sampled clear rate at 30M, but behind at 10M and 100M. Its greedy
policy is markedly worse at 30M and 100M. This points to a larger preview
being at least as hard to turn into a stable action rule under this model, not
to a clear increase in useful planning information. Since this is one seed for
the 12x12 variant, the result is directional rather than a definitive
architecture comparison.

The full-information pursuit controller clears 99.76% on this evaluation
suite. Both frontier variants therefore remain local exploration heuristics;
the extra perimeter does not solve the longer-horizon planning problem.

## Artifacts

- training run: `learning-runs/sleep-explore-ring12-v1-100m-seed0/`
- final fresh evaluation: `results/sleep-explore-ring12-v1-100m-seed0-fresh-test.json`
- checkpoint curve: `results/sleep-explore-ring12-v1-checkpoints-fresh-test.json`
- build target: `make -C gpu-d1 build/learn_sleep_explore_ring12.so`
