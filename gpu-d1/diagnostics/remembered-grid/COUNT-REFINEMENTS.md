# Finer counts and boundary crossings

Two follow-ups to the five-count 4x4 global summary. Both retain the same detailed 15x15 local observation, player statistics/position, 19 masked actions, coarse convolutional reader, and training protocol. They use exact remembered observations; no route distances or search results enter the policy.

## Representations

- **`counts2`**: five counts in each 2x2 block instead of 4x4. Seen, frontier, floor, wall and stairs are normalized by block area (4 instead of 16). The full 80x70 map becomes a 40x35 grid. Player markers, relative coordinates and within-block offsets use the new block size. The same coarse-reader dilations therefore cover a smaller physical radius; this is a resolution/compute comparison, not a pure information-only ablation.
- **`count_edges`**: retain the original five 4x4 counts and add eight known crossing counts, one for each neighboring block. A crossing is a one-tile step between two remembered floor tiles in different blocks. Cardinal block neighbors include straight crossings plus diagonal steps across their shared edge (up to 10 for a 4x4 edge). Diagonal block neighbors have one possible corner-to-corner crossing. Normalize each channel by its maximum. This matches the simulator's eight-direction movement, which does not forbid diagonal corner passage based on the two orthogonal cells.

A zero crossing count can mean either no passage or insufficient observed terrain. Only known floor endpoints count; unknown tiles do not count as floor. Map padding contributes neither floor nor crossings, and crossing counts never wrap around map edges. Enemy occupancy is not part of this static terrain summary.

The boundary features do **not** say which entrances connect to which exits inside a block, and do not calculate player reachability, routes, goals, or distances. Different internal geometries can still produce the same summary. The policy remains a convolutional grid policy, not a graph search controller.

At 80x70, the global arrays have 1,800 scalars for original counts, 7,000 for 2x2 counts, and 4,680 for counts plus crossings. The exact remembered terrain remains stored by the environment. Cache summaries until remembered terrain changes; recompute them immediately on change. Deterministic summary caching does not freeze any learned policy parameters.

## Protocol and checks

Seed 0, 12,000 updates, 3,072,000 sampled supervised examples, same expert/learner-state buffers and D4 augmentation as the prior screen. Select best validation checkpoint, then run the existing main/long synthetic regression suite, sampled main evaluation, paired distant-goal tests and global-feature erasure. Quality is measured on 32x32 maps. Full-size 80x70 AMP network-only PPO cost is benchmarked separately, with all policy parameters trainable; skip/recompute summary preprocessing are both timed. These are not PPO learning runs or full-size Crawl navigation tests.

`check_count_refinements.py` independently enumerates tile crossings, including diagonal steps, to check the vectorized summaries. It checks partial blocks, tiny arrays, all rotations/reflections, rectangular 80x70 inputs, cache behavior and gradients. The original compact-policy checks also pass.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_count_refinements.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/compact_suite.py refine_counts
```

The runner trains the two arms sequentially, then evaluates and benchmarks them. It retains only best/latest checkpoints per arm under ignored `learning-runs/remembered-grid/terrain-{counts2,count_edges}`. Logs are under that remembered-grid directory; checked results use the `results/remembered-grid-compact-{counts2,count_edges}` prefixes. Existing arms/checkpoints remain unchanged.
