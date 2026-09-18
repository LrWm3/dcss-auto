# Exact visited patterns on the compact 2x2 grid

This follow-up replaces the single visited fraction per 2x2 block with four binary channels: top-left, top-right, bottom-left, bottom-right. The five observed-terrain counts remain unchanged. Thus the model can distinguish visited trails that have equal counts but different shapes. It receives no distances, routes, arrows or hidden terrain. An inverse pixel shuffle can reconstruct the original visited bitmap exactly; the other terrain channels remain lossy count summaries.

The coarse spatial grid remains 16x16 on 32x32 training maps, and 40x35 on an 80x70 map. Global input channels increase from six to nine. The first dynamic convolution grows by 864 weights (three input channels times 32 filters times nine kernel elements); all other architecture, local observations, actions and training settings remain unchanged. Padding adds zero bits outside partial edge blocks.

Run `counts2_visit_bits`, seed 0, from scratch for 12,000 updates / 3,072,000 supervised examples, using the existing demonstration/learner-state mixture and validation checkpoint selection. Compare with the already completed 2x2 counts and 2x2 visited-count runs. Each policy collects its own trajectories. Equal seed does not give identical initial weights across different input dimensions. Quality is evaluated on held-out synthetic 32x32 layouts, plus longer-route and paired-goal panels. This is not a PPO learning run or an ordinary Crawl map evaluation.

Augmentation rotates/reflections the raw grid before packing bits, so bit positions always correspond to the transformed observation's top-left/top-right/bottom-left/bottom-right. The cache includes exact visited history and refreshes when it changes. Newly visited known terrain must invalidate the cache even without discovery; mere position changes or revisits do not alter its map input.

`check_visit_bits.py` independently enumerates bit positions, reconstructs the original visited bitmap including all D4 transforms and rectangular/partial-block inputs, distinguishes equal-count trails, checks cache invalidation, checks exclusion of visibility/enemies from the global summary, and verifies finite gradients. Existing visited-count and compact representation checks also pass.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_visit_bits.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/compact_suite.py visit_bits
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/visit_count_report.py --bits
```

Only best/latest checkpoints are retained under ignored `learning-runs/remembered-grid/terrain-counts2_visit_bits`. The 80x70 AMP benchmark separately estimates network-only PPO cost with all learned parameters trainable. It excludes environment, rollout, cache detection, replay buffer and GAE overhead. Summary reuse skips deterministic preprocessing during optimizer passes; it does not freeze learned layers.

## Interpretation

The exact-bit run improves greedy main known-stair and exploration success over both count-only comparisons. Relative to the visited-count model, gains are 6.25 and 3.91 percentage points. Longer known-stair success improves 5.47 points and longer threat backtracking improves from 28/32 to 32/32. On paired main episodes, exact bits rescue 37 known-stair failures while losing 21 previous successes, and rescue 41 exploration failures while losing 31.

This is a useful but mixed first result. Long exploration is 43.75%, below both visited counts (46.09%) and the original five counts (54.69%). Sampled main exploration is essentially unchanged/slightly lower (88.67% vs 89.45%), and long known-stair success remains low at 25.78%. Failures are timeouts rather than deaths; average immediate reversals remain high on long known-stair/exploration tests (314/251 per episode).

The representation demonstrably retains exact visited geometry, but one seed does not establish that the extra information caused a reproducible advantage: the first convolution has more parameters, initialization differs and learner trajectories differ. These results support further testing of exact trail information, not a claim that visited shape explains the original full-grid model's entire advantage. The global floor/wall/frontier/stair geometry is still aggregated into counts, so this is not an exact remembered-terrain encoder.

All 24 paired distant-goal tests pass; erasing the global representation reduces jointly correct pairs to zero. AMP reproduces the main greedy results exactly. Full-size network-only throughput is about 7,687/s, similar to the visited-count model's 7,633/s in this benchmark (not evidence of a meaningful speedup). Training took 193.7 seconds excluding validation; all learned parameters remain trainable in the precomputed-summary benchmark.

<!-- measured-results -->
## Results

| Global summary | Known stairs | Exploration | Long known stairs | Long exploration |
|---|---:|---:|---:|---:|
| counts2 | 49.22% | 75.78% | 16.41% | 54.69% |
| counts2_visits | 50.78% | 73.44% | 20.31% | 46.09% |
| counts2_visit_bits | 57.03% | 77.34% | 25.78% | 43.75% |

Greedy held-out exit rates. One seed does not establish robustness across training seeds.

| Global summary | Sampled known stairs | Sampled exploration | Main threat backtrack | Long threat backtrack |
|---|---:|---:|---:|---:|
| counts2 | 74.22% | 89.45% | 100.00% | 78.12% |
| counts2_visits | 76.56% | 89.45% | 100.00% | 87.50% |
| counts2_visit_bits | 77.73% | 88.67% | 100.00% | 100.00% |

| Global summary | Training seconds | Selected update | Goal pairs | Network-only PPO decisions/s |
|---|---:|---:|---:|---:|
| counts2 | 190.4 | 12,000 | 24/24 | 8,250 |
| counts2_visits | 195.2 | 12,000 | 24/24 | 7,633 |
| counts2_visit_bits | 193.7 | 12,000 | 24/24 | 7,687 |

Training seconds exclude validation. Throughput uses precomputed deterministic summaries, with all learned parameters trainable, AMP and four optimizer passes at batch 1024. It assumes preprocessing once per decision, excludes end-to-end PPO overhead, and was measured with no competing GPU jobs.

[Machine-readable summary and paired episode counts](../../results/remembered-grid-visit-bits-summary.json).
