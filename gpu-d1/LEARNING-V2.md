# Multi-map sleep/statistics learning task

This is the second controlled learning task. It extends the single-layout floor-clear task in [LEARNING.md](LEARNING.md) with three variables that can be measured independently:

- six native D:1 layouts, split into four training maps (1057, 1080, 1235, 1363) and two held-out maps (1589, 1609);
- sleeping monsters that wake when the player is within Chebyshev distance six, then pursue and attack on their speed schedule;
- four monster stat roles (normal, strong/slow, fragile/fast, heavy), randomized player HP, damage range, and hit rate, with all of those values exposed in the observation.

The proxy keeps the experiment tractable. Enemy positions are globally revealed, terrain is static, and the sleep rule has no line-of-sight or wandering component. It therefore tests multi-layout navigation, delayed engagement, and conditional combat, rather than native Crawl behavior.

## What was prepared

`scripts/compile_corpus.py` converts native headless exports into compact map binaries. It verifies the supported terrain and exhaustively checks all 5600 local line-of-sight origins before writing each map. The resulting corpus is in `fixtures/v2-corpus/`; `fixtures/v2-train/` and `fixtures/v2-test/` provide the fixed split used below. The corpus manifest records native seeds and binary hashes.

The v2 environment is in `src/learn_v2.cu` and `scripts/learn_env_v2.py`. The policy receives a 250-float observation: local floor and occupancy, per-monster relative position/HP/damage/speed/hit/awake state, and the player's own HP, damage range, hit rate, clock, and coordinates. `scripts/test_v2.py` runs 37 CPU/CUDA worlds for 900 mixed transitions and checks exact observations, masks, outputs, resets, sleep state, all six map IDs, and stat features.

The loader also accepts the 388-map corpus in `fixtures/d1-corpus-388/all/` (or
any split directory). It flattens fixed-width map tables and uses a 32-bit
row-offset table for variable-width distance fields, so the CUDA kernel keeps a
fixed-size descriptor instead of an eight-map pointer limit. The full corpus
was checked with CPU/CUDA parity on eight worlds and five transitions; the
distance buffer requires 64-bit pointer arithmetic once all 388 maps are
loaded.

To rebuild the corpus from the exported native layouts, repeat `--sources` for the three export batches:

```sh
gpu-d1/.venv/bin/python gpu-d1/scripts/compile_corpus.py \
  --sources gpu-d1/fixtures \
  --sources gpu-d1/fixtures/test-export-2 \
  --sources gpu-d1/fixtures/test-export-3 \
  --output gpu-d1/fixtures/v2-corpus
```

## Calibration and result

The initial eight-enemy calibration was too hard for this sparse-reward task. The controlled run uses four enemies and a robust proxy player (30 base HP, 1–8 damage, 90% hit before player variation). This leaves a meaningful engagement problem while keeping the scripted controller viable.

The held-out controls use 1,024 episodes on the two test maps:

| Controller | Clear rate | Enemies killed | Mean episode length |
|---|---:|---:|---:|
| Wait | 0.0% | 0.00 / 4 | 367 |
| Random valid action | 0.1% | 0.66 / 4 | 387 |
| Map-distance pursuit | 97.0% | 3.94 / 4 | 74 |

Three PPO seeds were trained for 10,027,008 decisions each (`learning-runs/v2-4e-10m`). The sampled policy was evaluated on 1,024 held-out episodes at each checkpoint:

| Decisions | Seed 0 | Seed 1 | Seed 2 |
|---:|---:|---:|---:|
| 0 | 0.1% | 0.2% | 0.1% |
| 1.0M | 0.9% | 0.0% | 0.2% |
| 3.0M | 5.1% | 2.5% | 4.4% |
| 10.0M | 12.6% | 14.3% | 12.5% |

At 10M, the seeds killed 1.7–2.0 enemies per episode on average. Greedy decoding was lower (2.0–4.7% clears), so the policy still relies on exploration at this horizon. The result is a clear learning signal, but a large gap remains between the learned policy and the hand-coded route-and-engage controller.

The final checkpoints were also evaluated for 2,048 episodes under shifted encounter strengths (`stat_mode=2`: stronger strong/slow and heavy roles, weaker fragile role, and shifted hit rates). Sampled clear rates were 8.5%, 8.9%, and 9.5% for seeds 0–2, compared with 12.1%, 14.5%, and 13.5% under the training stat regime. The broader player-stat regime (`player_mode=2`) produced 12.1%, 14.4%, and 13.3%, showing no material average drop in this run. The stat shift does cause more deaths (17–24% versus 5–9%), so the model is not invariant to encounter strength; it has a measurable but incomplete response to the exposed features.

## Reproduction

Build and validate the v2 library:

```sh
make -C gpu-d1 build/learn_v2.so
gpu-d1/.venv/bin/python gpu-d1/scripts/test_v2.py
```

Run the calibrated experiment:

```sh
gpu-d1/.venv/bin/python -u gpu-d1/scripts/train_v2.py \
  --train-corpus gpu-d1/fixtures/v2-train \
  --eval-corpus gpu-d1/fixtures/v2-test \
  --enemies 4 --steps 10000000 --seeds 0,1,2 \
  --output gpu-d1/learning-runs/v2-4e-10m
```

To train across the collected floor corpus, point the same entrypoint at its
fixed splits (the loader also accepts the corpus root and resolves `all/`):

```sh
gpu-d1/.venv/bin/python -u gpu-d1/scripts/train_v2.py \
  --train-corpus gpu-d1/fixtures/d1-corpus-388/train \
  --eval-corpus gpu-d1/fixtures/d1-corpus-388/validation \
  --enemies 8 --steps 10000000 --seeds 0,1,2 \
  --output gpu-d1/learning-runs/v2-d1-388-10m
```

Evaluate a checkpoint on the shifted stat regime:

```sh
gpu-d1/.venv/bin/python gpu-d1/scripts/evaluate_v2.py \
  --checkpoint gpu-d1/learning-runs/v2-4e-10m/seed-0/policy-10027008.pt \
  --stat-mode 2 --episodes 2048
```

The benchmark is evidence about this proxy task. It does not establish transfer to native DCSS: global enemy revelation, static geometry, simplified wakeup, and the map-distance heuristic remove major parts of the real search problem.
