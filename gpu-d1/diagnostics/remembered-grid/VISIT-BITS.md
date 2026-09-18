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
