# Corrected ring task: single map versus 256-map training

This is the first controlled floor-generalization comparison for the recent
ring setup. The player observation offset was corrected before either run: the
player block now begins after all `5 * enemy_slots` features. Both arms use the
same 40-enemy, 1024-decision task, six-tile sleep, remembered walls, corrected
11x11 ring, doubled first-seen floor reward, network, and PPO settings.

The single-map arm trained on the original fixture map (seed 1057). The
multi-map arm sampled uniformly from 256 training layouts. Both were trained
for 10,027,008 decisions with seed 0. The 32-map validation split remained
held out during training.

Commands:

```bash
gpu-d1/.venv/bin/python -u gpu-d1/scripts/train_sleep_explore_ring_walls_40.py \
  --enemies 40 --steps 10000000 --seeds 0 --eval-episodes 1024 \
  --output gpu-d1/learning-runs/ring-generalization-corrected-single-10m

gpu-d1/.venv/bin/python -u gpu-d1/scripts/train_sleep_explore_ring_walls_multi.py \
  --enemies 40 --steps 10000000 --seeds 0 --eval-episodes 1024 \
  --output gpu-d1/learning-runs/ring-generalization-corrected-multi-10m
```

The single-map arm ran at 204k decisions/s; the multi-map arm ran at 187k
decisions/s. The training evaluator's aggregate validation result was:

| Arm | Sampled clear | Sampled kills / 40 | Greedy clear |
| --- | ---: | ---: | ---: |
| Single map | 26.17% | 25.26 | 3.52% |
| 256 maps | 0.00% | 11.13 | 0.00% |

Those aggregate numbers are not enough for a generalization claim, so both
checkpoints were loaded into the same corrected multi-map evaluator and tested
with fixed map IDs. The original map used 1,024 episodes; the training panel
used 32 layouts with 64 episodes each; validation used all 32 layouts with 64
episodes each. The per-layout evaluator uses the same seed for both policies.

| Evaluation panel | Single-map clear | Multi-map clear | Single kills | Multi kills |
| --- | ---: | ---: | ---: | ---: |
| Original map 1057 | 30.37% | 0.00% | 27.50 | 14.30 |
| 32-map training panel | 0.68% | 0.00% | 8.09 | 11.38 |
| 32-map validation | 0.00% | 0.00% | 7.95 | 11.04 |

Only the original map produced any clears on the smaller panels: one of 32
training layouts for the single-map arm, and none for the multi-map arm or
either policy on validation. The multi-map policy kills more enemies on the
varied layouts but usually dies or times out before clearing all 40.

This result says that 10M decisions is below the learning threshold for the
256-layout version at this task difficulty. It does not show that multi-layout
training generalizes poorly: the varied-layout policy has not yet learned a
reliable clearing policy even on its training distribution. The single-map
policy's collapse away from map 1057 confirms strong memorization in this
regime, but the comparison needs a longer or easier multi-map run before it
can measure useful generalization.

The old single-map and new multi-map implementations produce exact CPU
transition, observation, mask, and output parity on map 1057 for 300 prescribed
actions. The ring wall semantic tests and CPU/CUDA parity tests also pass.

Artifacts: [single-map run](learning-runs/ring-generalization-corrected-single-10m), [multi-map run](learning-runs/ring-generalization-corrected-multi-10m), and [matched per-layout evaluation](learning-runs/ring-generalization-corrected-10m-matched-eval.json).
