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
