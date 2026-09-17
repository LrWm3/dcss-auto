# Remembered-grid execution optimization

Recommended: retain the trained spatial encoder and use `CroppedSpatialPolicy` with channels-last weights, FP16 autocast and `torch.compile`. The trained parameters load unchanged. Packed and narrower models remain experimental alternatives; they are not the replacement.

## Full-map compute measurements

Measured on Quadro RTX 5000 with Max-Q Design, PyTorch 2.6.0+cu124, 80x70 inputs. GPU process checks at benchmark start/end recorded no unrelated jobs. The earlier contended timing file is retained only under ignored learning-runs and is not used here.

| Configuration | Rollout inference / s | Training examples / s | Four-pass PPO compute decisions / s | Training peak allocated MiB |
|---|---:|---:|---:|---:|
| Original FP32 | 8,922 | 2,612 | 609 | 1,203 |
| Original + AMP | 12,826 | 5,479 | 1,238 | 888 |
| Cropped decoders + AMP | 25,742 | 10,636 | 2,410 | 371 |
| Cropped + AMP + compiler | 67,375 | 16,781 | 3,949 | 309 |
| Narrower + AMP + compiler | 80,533 | 21,131 | 4,958 | 182 |
| Cropped + AMP + compiler (batch 1024) | 67,697 | 18,688 | 4,370 | 1,168 |

Inference batches contain 512 observations; training minibatches contain 256 unless marked. The benchmark uses a shared actor/value head, clipped PPO policy loss, value loss, entropy, Adam, gradient clipping and dynamic AMP scaling. Four-pass rates are `1 / (inference_seconds_per_observation + 4 * training_seconds_per_example)`. Inputs are synthetic.

**These are network-only cost estimates, not measured end-to-end PPO throughput.** They exclude simulation, full-map observation export, rollout-buffer storage, GAE, replay anchors and evaluation. Peak memory excludes the simulator and rollout buffer. Compiler setup/autotuning is excluded from steady-state timings; warmup timings are recorded separately. A full-map learning result has not been established.

The earlier small-observation PPO reference was about 23,000 decisions/s end to end. These changes reduce the full-grid cost substantially but do not establish parity with that older representation.

## Navigation regression

Same original terrain-spatial checkpoint for the original and cropped models. No retraining is needed for the cropped decoder. This is the existing 32x32 regression suite, one seed; it is no longer a fresh architecture-selection test.

| Model | Known stairs, greedy | Exploration, greedy | Longer known stairs, greedy | Longer exploration, greedy | Paired goals correct |
|---|---:|---:|---:|---:|---:|
| Original | 92.19% | 90.23% | 53.91% | 67.19% | 24/24 |
| Cropped, compiled AMP | 92.19% | 90.23% | 53.91% | 67.19% | 24/24 |
| 2x2 packed, retrained | 37.89% | 62.89% | 10.94% | 41.41% | 24/24 |
| Narrower, retrained | 59.77% | 78.91% | 14.06% | 59.38% | 24/24 |

The 4x4 packed screen was stopped after its 4,000-update checkpoint: validation known-stair exits were 5.5%, versus 75% for the original terrain encoder at that stage. This was an early rejection for this budget, not proof it could never learn. The 2x2 and narrower screens each trained for 12,000 updates. Their training durations are not clean speed comparisons: unrelated GPU workloads affected the packed run.

## What changed

- The full map still enters the original spatial encoder. Only decoder work that cannot affect the player-centered 3x3 readout is omitted. A 9x9 intermediate patch and a 7x7 final patch cover the two pairs of decoder convolutions. Boundary masks reproduce the full-map padding rules.
- Optional FP16 autocast uses FP32 parameters, losses and returned logits, with a gradient scaler for training. Channels-last memory layout enables the faster convolution path.
- Compilation fuses preprocessing and small tensor operations. The compiled path exposes exact 2x2 max pooling as comparisons/selections, preserving the first-index tie rule.
- The full-resolution local view, remembered terrain semantics, action masks and policy input information are preserved. No route fields or teacher actions are introduced.
- Checkpoints now save the AMP scaler; old checkpoints remain readable. Model selection, replay sizes and demonstration budgets are unchanged.

## Verification

Output and parameter-gradient comparisons cover 32x32, 80x70 and irregular 37x31 shapes, including corners and near-edge positions. FP32 differences are at floating-point roundoff scale; AMP differences are checked separately. See the checked artifact below. Compiled navigation is evaluated using the original frozen weights.

## Reproduction

The compiler requires Python development headers compatible with the virtualenv interpreter. This machine lacked them; a matching `libpython3.12-dev` package was downloaded and extracted under ignored `learning-runs/remembered-grid/compiler-headers`, without changing system packages. Set `CPATH` to its `extracted/usr/include/python3.12` and `extracted/usr/include` directories, or use an environment with development headers installed.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_cropped.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/performance.py \
  --names original_fp32,original_amp,cropped_amp,cropped_compile,thin_compile \
  --output remembered-grid-performance-final.json
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/fast_finish.py \
  --architecture cropped --compile
```

The benchmark refuses to start on an occupied GPU by default. `--allow-contention` is for diagnostics only. Cold compilation may take minutes for new shapes; cached compiled kernels make repeated use cheaper. `run.py --architecture cropped --compile` enables the optimized path for a new supervised run; it does not implicitly load an old checkpoint.

[Compute measurements](../../results/remembered-grid-performance-final.json), [larger minibatch](../../results/remembered-grid-performance-batch1024.json), [navigation regression](../../results/remembered-grid-cropped.json), [precision checks](../../results/remembered-grid-cropped-checks.json).
