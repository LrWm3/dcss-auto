# Spatial map movement policy

Seed 0 trains from scratch to 100M decisions on the original fixed-map sleep
and exploration task. Actions are still the eight moves/melee directions and
wait. The reward is +1 per kill, +3 per clear, -1 per death, -0.001 per step,
and +0.002 per newly revealed floor cell in the 9x9 view. The initial view is
marked explored without reward. Eight enemies, sleep radius 6, the 256-decision
deadline and PPO settings are retained.

The observation contains the original 206 local/monster/scalar inputs plus
four 80x70 spatial channels: full static floor mask, explored floor mask,
player location, and living enemy HP divided by 16. Enemy positions were
already globally available in the original 206 inputs. The full explored mask
is new information compared with the ring. The ring itself is replaced by the
map channels. This is a joint representation and architecture experiment;
it does not isolate the effect of terrain alone or of convolutions alone.

The map encoder pads the height to 72, applies Conv2d(4,8,4,stride=4), ReLU,
Conv2d(8,16,3,stride=2,padding=1), ReLU, then flattens its 9x10 feature grid.
Those features join the original 206 inputs before two 128-unit tanh layers
and actor/value heads. No pathfinder supplies actions or labels to training.

Validation: 37 worlds over 301 mixed-action steps matched exactly between CPU
and CUDA, including state, observations, masks and rewards. Identical actions
also matched the ring task's states, rewards and original 206 inputs. Spatial
channel semantics and finite forward/backward policy gradients passed.

## Reproduction

```sh
make -C gpu-d1 build/learn_sleep_spatial.so
gpu-d1/.venv/bin/python gpu-d1/scripts/test_sleep_spatial.py
gpu-d1/.venv/bin/python -u gpu-d1/scripts/train_sleep_spatial.py \
  --enemies 8 --steps 100000000 --seeds 0 \
  --output gpu-d1/learning-runs/sleep-spatial-v1-100m-seed0
gpu-d1/.venv/bin/python gpu-d1/scripts/report_sleep_spatial.py \
  gpu-d1/learning-runs/sleep-spatial-v1-100m-seed0 \
  --output gpu-d1/results/sleep-spatial-v1-100m-seed0-fresh-test.json
```

The report evaluates 10M, 30M and 100M checkpoints on 2,048 episodes per mode
using evaluation seed 1200000, matching the prior ring reports. These are fresh
relative to training, but the suite has been reused across experiments, so it
is a validation suite rather than an untouched final test. Results apply to
random placements and combat on this one map, not to unseen maps or real DCSS.

## Fresh results

The seed-0 checkpoints were evaluated on 2,048 episodes with evaluation seed
1,200,000. The frontier-ring seed-0 numbers are included as the matched
reference.

| representation | decisions | sampled clear | sampled kills | greedy clear | sampled timeout |
|---|---:|---:|---:|---:|---:|
| frontier ring | 10M | 19.87% | 6.47 | 16.06% | 78.91% |
| spatial map | 10M | 7.91% | 5.59 | 6.20% | 91.21% |
| frontier ring | 30M | 36.33% | 6.94 | 33.40% | 62.60% |
| spatial map | 30M | **40.63%** | **7.08** | **36.77%** | **58.54%** |

The full spatial representation learns more slowly, but by 30M it slightly
exceeds the matched seed-0 ring checkpoint. This is only one seed and one map,
so it is evidence that spatial encoding is viable rather than evidence that it
is superior. The result also shows why the 10M comparison alone would have
been misleading: the spatial encoder pays an optimization cost for its larger
representation, then catches up with longer training.
