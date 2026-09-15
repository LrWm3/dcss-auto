# Sleep task with first-seen floor-cell reward

This ablation keeps the original 206-float observation and all sleep-only task rules. The only change is a compile-time reward term: each floor cell entering the existing 9x9 observation window for the first time in an episode contributes `+0.001`. The initial 9x9 view is marked seen without reward, and revisits contribute nothing. The seen set is internal state; it is not exposed to the policy.

The fixed map has 836 floor cells, so the total exploration bonus is bounded by `+0.836` per episode. The binary was built with `-DSLEEP_ON -DEXPLORE_REWARD`.

## 10M result

Each seed ran to 10,027,008 decisions. The separate evaluation suite contains 2,048 episodes with root seed 1,200,000.

| Policy | Sampled clear | Sampled kills / 8 | Sampled timeout | Greedy clear | Greedy kills / 8 |
|---|---:|---:|---:|---:|---:|
| Sleep-only, seed 0 | 1.27% | 4.41 | 97.9% | 0.29% | 3.77 |
| Sleep-only, seed 1 | 2.20% | 4.54 | 97.3% | 0.93% | 4.08 |
| Sleep-only, seed 2 | 0.93% | 4.09 | 98.1% | 0.20% | 3.52 |
| First-seen reward, seed 0 | 1.27% | 4.28 | 97.6% | 0.29% | 3.81 |
| First-seen reward, seed 1 | 0.73% | 4.17 | 98.4% | 0.63% | 3.94 |
| First-seen reward, seed 2 | 0.44% | 4.01 | 98.8% | 0.20% | 3.81 |

Across seeds, sampled clear rate fell from 1.46% to 0.81%, and mean kills fell from 4.35 to 4.16. The pursuit controller remained near-perfect, so the reward change did not make the task unsolvable. It changed the learned policy without producing more floor clears.

## What changed in trajectories

On a matched 2,048-episode diagnostic suite using root seed 1,300,000 and the seed-0 10M checkpoints, timeout episodes had these averages:

| Controller | Kills | Unique positions | Steps near a live enemy | Enemy slots woken |
|---|---:|---:|---:|---:|
| Sleep-only | 4.40 | 111.9 | 23.4% | 4.43 |
| First-seen reward | 4.26 | 102.8 | 23.2% | 4.29 |

The bonus did not produce broader useful travel. Since the seen set is hidden from the policy, identical observations can produce different rewards depending on the episode history. That adds partial observability to the reward without giving the model memory of what it has already explored. The reward also pays for any newly viewed floor, whether or not it leads toward a sleeping enemy, so it is only indirectly aligned with floor completion.

This first pass gives no evidence that a global first-seen bonus improves the sleep task. A better exploration signal would either expose a compact visited-state summary or shape progress toward currently living targets, while keeping the terminal clear reward dominant.

## Reproduction

```sh
make -C gpu-d1 build/learn_sleep_explore.so

gpu-d1/.venv/bin/python -u gpu-d1/scripts/train_sleep_explore.py \
  --enemies 8 --steps 10000000 --seeds 0,1,2 \
  --output gpu-d1/learning-runs/sleep-explore-v1-10m

gpu-d1/.venv/bin/python gpu-d1/scripts/report_sleep_explore.py \
  gpu-d1/learning-runs/sleep-explore-v1-10m \
  --output gpu-d1/results/sleep-explore-v1-10m-fresh-test.json
```

The raw training log is `results/sleep-explore-v1-10m-console.log`; the evaluation is `results/sleep-explore-v1-10m-fresh-test.json`.
