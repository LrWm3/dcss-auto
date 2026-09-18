# Finer counts and boundary crossings

Two follow-ups to the five-count 4x4 global summary. Both retain the same detailed 15x15 local observation, player statistics/position, 19 masked actions, coarse convolutional reader, and training protocol. They use exact remembered observations; no route distances or search results enter the policy.

## Representations

- **`counts2`**: five counts in each 2x2 block instead of 4x4. Seen, frontier, floor, wall and stairs are normalized by block area (4 instead of 16). The full 80x70 map becomes a 40x35 grid. Player markers, relative coordinates and within-block offsets use the new block size. The same coarse-reader dilations therefore cover a smaller physical radius; this is a resolution/compute comparison, not a pure information-only ablation.
- **`count_edges`**: retain the original five 4x4 counts and add eight known crossing counts, one for each neighboring block. A crossing is a one-tile step between two remembered floor tiles in different blocks. Cardinal block neighbors include straight crossings plus diagonal steps across their shared edge (up to 10 for a 4x4 edge). Diagonal block neighbors have one possible corner-to-corner crossing. Normalize each channel by its maximum. This matches the simulator's eight-direction movement, which does not forbid diagonal corner passage based on the two orthogonal cells.

A zero crossing count can mean either no passage or insufficient observed terrain. Only known floor endpoints count; unknown tiles do not count as floor. Map padding contributes neither floor nor crossings, and crossing counts never wrap around map edges. Enemy occupancy is not part of this static terrain summary.

The boundary features do **not** say which entrances connect to which exits inside a block, and do not calculate player reachability, routes, goals, or distances. Different internal geometries can still produce the same summary. The policy remains a convolutional grid policy, not a graph search controller.

At 80x70, the global arrays have 1,800 scalars for original counts, 7,000 for 2x2 counts, and 4,680 for counts plus crossings. The exact remembered terrain remains stored by the environment. Cache summaries until remembered terrain changes; recompute them immediately on change. Deterministic summary caching does not freeze any learned policy parameters.

## Original-model comparison caveat

The original spatial encoder receives global visited-tile history and current visibility/player channels in addition to terrain. Count-based models do not receive these globally. Known-stair fixtures initialize a walked history from the goal to the starting position, making visited history potentially informative. Comparisons among count variants keep this omission fixed; differences from the original model cannot be attributed solely to tile geometry.

`check_global_visits.py` is a supplementary post-training intervention on the original checkpoint: remove only its global visited channel, leaving local visited observations and all other channels intact. This can measure reliance on the feature but is not a substitute for retraining without it.

## Interpretation

Finer 2x2 counts improved every main/long navigation exit metric in this one-seed screen. The gain is meaningful as a first result, but known-stair long routes remain poor (16.41%). Boundary crossing counts did not help overall at the same training budget; this does not show that boundary information is inherently useless. The current summary omits connectivity inside blocks, and the added features also change optimization.

Sampling helps: 2x2 counts reach 74.22% known-stair and 89.45% exploration success, versus 49.22% and 75.78% greedy. Greedy failures are timeouts, with many immediate movement reversals. All three count variants solve both members of all 24 distant-goal pairs; erasing global input drops that to zero pairs. They use global information, but that does not establish robust route planning. AMP reproduces 2x2 greedy results exactly and changes the boundary arm's exploration result by one episode.

The finer grid costs about 2.39 times as much network time per decision as original counts at full map size (8,250 vs 19,682 estimated decisions/s). It is still faster than the earlier optimized spatial reference (4,370/s), with substantially weaker greedy navigation. The boundary arm is 17,623/s. Training on the small maps took 190 and 231 seconds, excluding validation; small-map training timing should not be extrapolated to full-size maps.

### Additional visited-history diagnostic

Removing only the original spatial model's **global visited channel**, while preserving local visited information and the rest of its inputs, changes known-stair exits from **92.19% to 0.78%**, exploration from **90.23% to 0.39%**, and threat-backtrack from **100% to 9.38%**. The original checkpoint relies heavily on this channel. This is an out-of-distribution intervention, not evidence that an appropriately retrained model cannot navigate without it, nor a quantitative decomposition of the gap between architectures.

[Raw intervention results](../../results/remembered-grid-global-visits-ablation.json). A useful next matched-input test would add visited-tile counts to the compact summaries, then compare against an original encoder trained with the same global information. Current count-variant comparisons are unaffected by this caveat.

## Protocol and checks

Seed 0, 12,000 updates, 3,072,000 sampled supervised examples, same expert/learner-state buffers and D4 augmentation as the prior screen. Select best validation checkpoint, then run the existing main/long synthetic regression suite, sampled main evaluation, paired distant-goal tests and global-feature erasure. Quality is measured on 32x32 maps. Full-size 80x70 AMP network-only PPO cost is benchmarked separately, with all policy parameters trainable; skip/recompute summary preprocessing are both timed. These are not PPO learning runs or full-size Crawl navigation tests.

`check_count_refinements.py` independently enumerates tile crossings, including diagonal steps, to check the vectorized summaries. It checks partial blocks, tiny arrays, all rotations/reflections, rectangular 80x70 inputs, cache behavior and gradients. The original compact-policy checks also pass.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_count_refinements.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/compact_suite.py refine_counts
```

The runner trains the two arms sequentially, then evaluates and benchmarks them. It retains only best/latest checkpoints per arm under ignored `learning-runs/remembered-grid/terrain-{counts2,count_edges}`. Logs are under that remembered-grid directory; checked results use the `results/remembered-grid-compact-{counts2,count_edges}` prefixes. Existing arms/checkpoints remain unchanged.

<!-- measured-results -->
## Measured results

| Summary | Known stairs | Exploration | Long known stairs | Long exploration |
|---|---:|---:|---:|---:|
| counts | 37.50% | 63.67% | 11.72% | 33.59% |
| counts2 | 49.22% | 75.78% | 16.41% | 54.69% |
| count_edges | 36.72% | 52.34% | 4.69% | 37.50% |

Greedy held-out exits. Main tasks have 256 episodes each; long tasks have 128 each. Original 4x4 counts are reused from the previous screen. One training seed does not measure seed variability.

| Summary | Training seconds | Selected update | Goal pairs correct | Network-only PPO decisions/s |
|---|---:|---:|---:|---:|
| counts | 183.1 | 12,000 | 24/24 | 19,682 |
| counts2 | 190.4 | 12,000 | 24/24 | 8,250 |
| count_edges | 231.2 | 12,000 | 24/24 | 17,623 |

Training time excludes validation. Each arm receives 3,072,000 supervised examples; learner-state collection differs. Network estimates use precomputed deterministic summaries, AMP, batch 1024 and four optimizer passes, with every learned parameter trainable. They exclude environment, rollout, GAE and buffer overhead. Quality uses fresh summaries; no stale-cache quality is assumed.

[Raw summary](../../results/remembered-grid-count-refinements-summary.json).
