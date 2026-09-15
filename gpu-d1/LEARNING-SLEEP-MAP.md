# Sleep task with the full static map exposed

This is the first observation ablation after the sleep-only trajectory diagnosis. It keeps the fixed native map, six-tile sleep radius, eight enemies, combat, reward, 256-decision deadline, PPO settings, and three seeds unchanged. The only task-side change is appending the static 80x70 floor mask (5,600 binary values) to the original 206-float observation. The policy therefore receives 5,806 inputs. The map is written by the CUDA observation kernel, so CPU and GPU transitions remain exact.

## 10M result

Each seed ran to 10,027,008 decisions. The fresh evaluation suite contains 2,048 episodes with root seed 1,200,000.

| Policy | Sampled clear | Sampled kills / 8 | Sampled timeout | Greedy clear | Greedy kills / 8 |
|---|---:|---:|---:|---:|---:|
| Sleep-only, seed 0 | 1.27% | 4.41 | 97.9% | 0.29% | 3.77 |
| Sleep-only, seed 1 | 2.20% | 4.54 | 97.3% | 0.93% | 4.08 |
| Sleep-only, seed 2 | 0.93% | 4.09 | 98.1% | 0.20% | 3.52 |
| Full map, seed 0 | 0.15% | 3.33 | 98.4% | 0.15% | 2.57 |
| Full map, seed 1 | 0.49% | 4.00 | 98.3% | 0.15% | 3.18 |
| Full map, seed 2 | 0.05% | 2.73 | 98.8% | 0.00% | 2.15 |

Across seeds, sampled clear rate fell from 1.46% to 0.23% and mean kills fell from 4.35 to 3.35. The pursuit controller remains near-perfect (99.76% clear for the sleep-only task and 99.76% in this suite), so the environment and deadline still permit completion.

The result does not show that terrain information is intrinsically useless. The flat MLP now has 5,806 input features but the same two 128-unit hidden layers, and the full map is constant across every episode. That creates roughly 29 times as many first-layer weights while giving the network no spatially structured way to combine a player location with nearby map cells. At 10M decisions, the larger model may simply be harder to optimize. The map input also cannot by itself provide visited-state memory.

The appropriate conclusion from this pass is narrower: **adding a raw global map to the existing MLP does not solve the sleep task within 10M decisions and currently makes learning worse.** A useful follow-up would encode player-centered map geometry or use a spatial encoder, while measuring compute-matched training rather than treating this flat concatenation as a definitive test of global geometry.

## Reproduction

```sh
make -C gpu-d1 build/learn_sleep_map.so

gpu-d1/.venv/bin/python -u gpu-d1/scripts/train_sleep_map.py \
  --enemies 8 --steps 10000000 --seeds 0,1,2 \
  --output gpu-d1/learning-runs/sleep-map-v1-10m

gpu-d1/.venv/bin/python gpu-d1/scripts/report_sleep_map.py \
  gpu-d1/learning-runs/sleep-map-v1-10m \
  --output gpu-d1/results/sleep-map-v1-10m-fresh-test.json
```

The raw training log is `results/sleep-map-v1-10m-console.log`; the fresh evaluation is `results/sleep-map-v1-10m-fresh-test.json`.
