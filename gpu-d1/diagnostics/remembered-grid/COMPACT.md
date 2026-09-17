# Position-aware compact map representations

The first screen does not produce a replacement for the original spatial model. Attention preserves exploration quality but loses substantial known-stair route competence and is expensive to train end to end. The learned coarse grid and count grid are much faster, with similar but substantially weaker navigation at this budget.

The count result is informative: all 24 distant-goal pairs are solved, but broader routing succeeds much less often. This establishes use of remote goal information, not retention of detailed connectivity. Main-map failures for the coarse/count policies are timeouts, with frequent reversals, rather than deaths. Their late validation improvement and the single seed prevent conclusions about eventual learning limits. The count representation demonstrably aliases different within-block geometries; these results do not isolate that loss from training difficulty or other architecture changes.

For a next targeted change, smaller blocks or a small amount of information about block-edge connectivity would be more directly motivated than simply enlarging the count-reader network. The count summary could also supplement a detailed local or intermediate-scale view rather than replace all remote geometry.

<!-- compact-results:start -->
## Results

| Representation | Known stairs | Exploration | Longer known stairs | Longer exploration | Goal pairs |
|---|---:|---:|---:|---:|---:|
| Original spatial | 92.19% | 90.23% | 53.91% | 67.19% | 24/24 |
| Previous cached reader, fresh terrain | 69.14% | 91.41% | 32.03% | 63.28% | 24/24 |
| attn | 57.03% | 92.58% | 15.62% | 68.75% | 24/24 |
| coarse | 40.62% | 65.23% | 10.94% | 35.16% | 21/24 |
| counts | 37.50% | 63.67% | 11.72% | 33.59% | 24/24 |

Greedy exits on the same regression splits. Main known/exploration each contain 256 episodes; long each contain 128. Paired-goal erasure results and sampled/AMP outcomes are in the summary JSON. The earlier cached paired-goal result used interval 4; the statistic measures the first action after cache initialization, so refresh interval does not alter that readout.

| Representation | Training seconds (excludes validation) | Collected decisions | Selected update |
|---|---:|---:|---:|
| attn | 415.2 | 968,329 | 12,000 |
| coarse | 184.1 | 1,129,133 | 12,000 |
| counts | 183.1 | 1,142,554 | 12,000 |

All arms used 3,072,000 sampled supervised examples. Collected decisions differ because learner trajectories differ.

| Full-map network-only PPO estimate | Trainable encoder, refresh every decision | Frozen encoder, refresh every decision | Frozen encoder, one refresh per 4 decisions |
|---|---:|---:|---:|
| attn | 1,193/s | 4,662/s | 5,836/s |
| coarse | 12,511/s | 16,301/s | 16,937/s |
| counts | 15,778/s | 19,682/s | 20,757/s |

Previous optimized spatial reference: 4,370/s with a trainable encoder, AMP and compilation, batch 1024. New models use AMP without compilation, the same training batch size, and the same four-pass cost formula. Freezing changes what can learn. The count encoder has no trainable parameters: its precomputed-input ("frozen") column still trains every learned parameter, merely skipping deterministic count pooling on each replay presentation. None of these numbers include simulator or rollout overhead. Quality at stale refresh intervals has not been measured in this screen.

[Machine-readable summary](../../results/remembered-grid-compact-summary.json).
<!-- compact-results:end -->

This screen compares three new representations with the existing spatial model and the cached 3x3-readout prototype. All retain the detailed 15x15 local view and the same 19 masked actions. No route-distance fields, frontier arrows, teacher actions, or hidden terrain enter policy observations.

## Three variants

- **Attention (`attn`)**: the same player-independent, three-channel terrain U-net as the cached prototype. Read a detailed 3x3 feature patch at the player, and use two four-head attention stages to read 4x4-pooled map features. Queries include local observations, local map features, HP, time and player position. Keys/values include map-feature displacement from the player. Moving the player changes the reader, without invalidating the terrain encoding.
- **Dynamic coarse map (`coarse`)**: pack each 4x4 terrain block into 48 channels, then project to 24 learned features. Packing preserves each input tile's identity; the learned projection can lose information. Each decision, run three small convolutions over the coarse grid, conditioned on relative player coordinates and a player-cell marker. Combine a 3x3 coarse patch with a 4x4 pooled global readout. The full-size 80x70 map produces a 20x18 coarse grid, with zero padding at its bottom edge.
- **Counts only (`counts`)**: replace the learned terrain-block features with exactly five counts per 4x4 block: seen, frontier, floor, wall, stairs. Counts are divided by 16 for input scaling. The dynamic coarse reader is otherwise the same as `coarse`. No within-block global geometry is available. Local detailed vision remains available.

“Seen” means observed at least once, including observed walls, not visited by the player. A frontier is a known floor tile with at least one unknown tile among its eight in-array neighbors. This uses only remembered observations; it does not inspect whether unknown tiles are actually passable. Array padding does not create frontier neighbors and contributes zero to block counts. Floor and wall are disjoint in simulator observations; seen count is intentionally redundant with their sum. Stair count overlaps floor count.

## Cache and learning

The static cache depends only on remembered floor, wall and stairs. Refresh every changed map immediately. Player movement, current visibility, and local enemies do not invalidate unchanged terrain. There are no intentionally stale observations in this screen.

Supervised updates train the whole model, including the map encoder. Inference caches must be invalidated after parameter updates or environment resets. The training runner calls uncached forward directly, so stale weights and detached features cannot silently suppress encoder learning. Evaluation uses the exact-change cache. The screen does not run PPO finetuning.

## Controlled protocol

Each arm uses seed 0, 12,000 supervised updates, 256 sampled examples per update, the existing expert/learner-state buffer mixture, and D4 augmentation. Each collects its own learner trajectories. Select the checkpoint using mean success across the three validation scenario kinds. Report greedy main/long regression results, sampled main results with a common evaluation seed, paired distant-goal tests, and the global-readout erasure intervention.

The maps remain the existing 32x32 synthetic navigation regression suite. This is not a fresh test set after earlier representation experiments and does not establish full-size Crawl navigation, general combat, or statistical significance. The selected checkpoint may precede the last training update. Report total training time excluding validation, collected decisions, and supervised examples separately.

Benchmark synthetic 80x70 actor/value computation with AMP, inference batch 512, training batch 1024, four PPO passes, optimizer, clipping and loss scaling. Report encoder and per-decision reader costs separately. Benchmark both fully trainable and frozen static encoders. For the count arm, the static pooling has no learned parameters; the “frozen” case merely precomputes the counts. Refresh intervals 1/4/8 in the cost formula are hypothetical amortization scenarios, not tested stale-map policies. Exclude simulator, change detection, rollout storage and GAE. Also evaluate the selected checkpoint under AMP to check the precision used in timing.

## Checks and commands

`check_compact.py` checks counts against an independent tile loop, frontier boundary rules, intentional count aliasing between different geometries, 32x32 and 80x70 shapes, position-sensitive outputs, cache equivalence/invalidation, and finite training gradients.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_compact.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/run.py --arm terrain --architecture attn --updates 12000
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/compact_suite.py remaining
```

The last command trains `coarse` and `counts`, then evaluates and benchmarks all three. Run sequentially on an otherwise idle GPU. For individual evaluations use `compact_suite.py quality --kind counts` (or `attn`/`coarse`); use `benchmark` for timing. Checkpoints are bounded to best/latest under ignored `learning-runs/remembered-grid/terrain-{kind}`. Checked result JSONs are under `results/remembered-grid-compact-*`.
