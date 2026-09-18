# Visited-tile counts in compact global summaries

The previous original-model intervention found strong reliance on global visited history. This experiment adds a sixth block channel to each compact count model: the number of tiles actually stepped on, divided by the block area. Seen terrain and visited terrain remain distinct. It does not add routes, distances, frontier arrows, current global enemy positions, or global visibility.

Two new seed-0 arms, `counts_visits` (4x4) and `counts2_visits` (2x2), are trained from scratch for the same 12,000 updates / 3,072,000 supervised samples as their existing no-global-visits counterparts. The existing teacher/learner-state mixture, D4 augmentation, map splits, local observation, action space and checkpoint selection rule remain fixed. Each model collects its own learner trajectories; this is equal-budget training, not identical training data. Known-stair fixtures retain their real preceding walk from goal to start, so visited history can be informative about the route.

The sixth input slightly increases the first convolution's parameter count. Everything else in the network is unchanged. The exact map cache now includes visited history in its key: newly visiting a known floor tile refreshes that world's summary even if no new terrain becomes visible. Revisiting a tile does not change its count. Each block's value remains normalized by full block area, including edge blocks whose absent cells contribute zero.

`check_visit_counts.py` checks independently enumerated counts, partial blocks, all eight rotations/reflections, full-size rectangular maps, gradients, and cache refresh on newly visited tiles. Existing representation checks must still pass. Only best/latest checkpoints are retained in ignored learning-runs folders.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_visit_counts.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/compact_suite.py visits
```

Evaluation uses the same main and long synthetic navigation tests, sampled evaluation, paired distant goals, global-input erasure, and AMP regression. Main task groups have 256 episodes each, long groups 128, threat groups 32. Training occurs on 32x32 synthetic geometry, not ordinary Crawl maps. These are supervised / learner-state demonstration runs, not PPO training. Separate 80x70 network-only PPO cost measurements exclude environment, cache detection, rollout, buffer and GAE overhead. Deterministic summary caching preserves training of all learned parameters.

## Interpretation

No clear overall improvement at this budget. On main greedy evaluation, 4x4 visits changes known-stair/exploration success by -1.95/-3.12 percentage points; 2x2 visits changes them by +1.56/-2.34 points. Long 2x2 known-stair navigation improves 3.91 points while long exploration declines 8.59 points. Sampled 2x2 exploration is unchanged at 89.45%; sampled known-stair success rises 2.34 points. Threat backtracking remains perfect on the main suite, with some improvement on longer threat layouts.

The episode pairing shows gains and losses rather than systematic rescue: 2x2 visits rescues 32 main known-stair failures but loses 28 previous successes; for exploration it rescues 37 and loses 43. These are results from one training seed, not a robust causal estimate over training randomness. Equal seeds do not make weights or learner-state datasets identical across different input dimensions.

Both new models solve all 24 paired distant-goal tests, falling to zero jointly correct pairs when global input is erased. AMP reproduces both new models' main greedy results exactly. The test suite failures are timeouts, not deaths. The known-stair greedy policies still make many immediate movement reversals (129 per episode for 4x4 visits and 98 for 2x2 visits), compared with much shorter successful routes.

The earlier original-model channel erasure established reliance on detailed global visited history. These new runs show that simply supplying an aggregate visited count does not recover its advantage under this training procedure. They do not establish that count summaries are incapable of learning it, nor that exact trail shape is the only missing ingredient. A possible next controlled test is to keep 2x2 terrain counts but replace the one visited count with four within-block visited bits, preserving exact trail shape without increasing spatial grid size. This would be a new experiment; it has not been run here.

Measured full-map network-only estimates are 18,819/s for 4x4 visits and 7,633/s for 2x2 visits, versus prior 19,682/s and 8,250/s. Treat the small differences as benchmark observations, not precision hardware claims. Training took 182 and 195 seconds excluding validation. All old/new comparisons retain their respective original result artifacts.

<!-- measured-results -->
## Results

| Global summary | Known stairs | Exploration | Long known stairs | Long exploration |
|---|---:|---:|---:|---:|
| counts | 37.50% | 63.67% | 11.72% | 33.59% |
| counts_visits | 35.55% | 60.55% | 6.25% | 33.59% |
| counts2 | 49.22% | 75.78% | 16.41% | 54.69% |
| counts2_visits | 50.78% | 73.44% | 20.31% | 46.09% |

Greedy held-out exit rates. One seed does not establish robustness across training seeds.

| Global summary | Sampled known stairs | Sampled exploration | Main threat backtrack | Long threat backtrack |
|---|---:|---:|---:|---:|
| counts | 61.72% | 66.80% | 100.00% | 65.62% |
| counts_visits | 65.62% | 63.67% | 100.00% | 68.75% |
| counts2 | 74.22% | 89.45% | 100.00% | 78.12% |
| counts2_visits | 76.56% | 89.45% | 100.00% | 87.50% |

| Global summary | Training seconds | Selected update | Goal pairs | Network-only PPO decisions/s |
|---|---:|---:|---:|---:|
| counts | 183.1 | 12,000 | 24/24 | 19,682 |
| counts_visits | 182.2 | 12,000 | 24/24 | 18,819 |
| counts2 | 190.4 | 12,000 | 24/24 | 8,250 |
| counts2_visits | 195.2 | 12,000 | 24/24 | 7,633 |

Training seconds exclude validation. Throughput uses precomputed deterministic summaries, with all learned parameters trainable, AMP and four optimizer passes at batch 1024. It assumes preprocessing once per decision, excludes end-to-end PPO overhead, and was measured with no competing GPU jobs.

[Machine-readable summary and paired episode counts](../../results/remembered-grid-visit-counts-summary.json).
