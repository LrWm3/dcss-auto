# Native-scale demonstration curriculum

Follow-up to SYMBOLIC-PPO-SCALE.md. The small-map PPO correction survived 3M
in two seeds, but transferred poorly to native 80x70 geometry. This screen asks
whether demonstrations on native geometry can establish navigation before PPO.
It does not isolate curriculum from native demonstrator exposure.

## Fixed design

- Same 64 train / 16 validation / 32 test native layouts, with disjoint geometry.
- Same 15x15 local crop, 16x16 coarse global map, GRU128 and 19 primitive actions.
- No enemies, route hints, distance inputs or frontier features. Controller
  actions supervise the policy; routes are not observation fields.
- Initialize from small-map corrected PPO seed 0 at 3M, not the unsuccessful
  1M full-size PPO continuation.
- Generate four start/goal pairs per layout per band: 4–12, 12–24, 24–128
  shortest-path steps to the primary stair. Two neighboring usable stairs can
  shorten the actual trip. Each pair has known-stair and exploration variants.
- Known stairs are recorded by a real traversed history. Exploration begins
  without that history. Short initial goal distance does not guarantee a short
  exploration episode: the agent may search in the wrong direction.
- Fixed fixture RNG per split and band; no geometry copies. All observations
  already use the native 80x70 canvas, including the first stage.
- Physical deadline 1024; collected training fragments capped at 512 steps.
  This cap bounds collection cost and is not an artificial terminal target:
  imitation uses action labels, not return bootstrapping.
- Two buffers of 1024 sequences, each with 16 burn-in and 16 learning steps.
  Cache deterministic symbolic inputs in float32, not learned encoder features.
  Burn-in has no gradients; terminal padding is excluded. Batch 16 per buffer.
- Half the loss is expert-buffer cross-entropy; half is learner-buffer labels.
  Refresh learner examples every 100 updates using teacher/learner action
  mixtures, reducing teacher probability from about .5 toward .1. Refresh pure
  demonstrations every 500 updates. Adam lr1e-4, AMP, gradient clip1.
- No geometric augmentation in this initial screen. No frozen navigation layers.
- Up to 2000 updates per stage; validate every 500. Advance after known-stair
  success >=85% and exploration >=75% in stage 0; >=80% / >=65% in later stages.
  Restore the selected validation checkpoint before progressing. A passing
  checkpoint takes precedence over a prior higher mean that fails one gate.
- If a stage fails, stop progression and inspect results. Test scores do not
  select checkpoints. The original full-size test set is evaluated before/after;
  the final attempted band's test set is also evaluated.
- If all stages pass, try a bounded corrected PPO continuation (detached critic,
  lambda=1), to test the imitation-to-PPO handoff separately.

## Implementation and verification

`native_curriculum.py` generates only scene rows; existing map arrays and native
library are reused. Outputs/checkpoints live under ignored training folders.
The smoke run checks native fixture initialization, valid controller labels,
sequence padding, a finite supervised loss, and an actual optimizer update.
Its first update changed 34 state-dict tensors (including shared GRU aliases),
with 30 optimizer parameter states. This is a functional screen, not a claim
that learning or generalization has already succeeded.

Run with the compiler-header CPATH documented in EXECUTION-OPTIMIZATION.md:

```sh
python native_curriculum.py --name native-curriculum-seed0
```

The trainer refuses to overwrite checkpoints and holds a run lock. Fixed buffer
sizes and stage-best/latest/selected checkpoints bound disk and memory usage.

## Initial screen results

Stage 0 passed at 1000 updates. Stage 1 did not pass after 2000 updates; stage 2
and the conditional PPO handoff were therefore not launched. The selected
checkpoint is stage 1 at 2000 updates, chosen by validation mean success.

| Stage validation | Before stage: known / explore | Selected: known / explore |
|---|---:|---:|
| 4–12 steps | 67.19% / 59.38% | 85.94% / 76.56% |
| 12–24 steps | 40.62% / 54.69% | 64.06% / 68.75% |

Middle-band held-out test success was 64.84% known stairs and 69.53% exploration
(128 scenarios per condition), close to its validation result.

On the **original** 24–128-step native test set, despite no training on the
longest curriculum band:

| Greedy metric | Original source | Curriculum checkpoint |
|---|---:|---:|
| Known stairs: success | 7.03% | 31.25% |
| Known stairs: mean additional turns | 920.91 | 724.55 |
| Known stairs: mean reversals | 650.50 | 471.88 |
| Exploration: success | 25.78% | 56.25% |
| Exploration: mean additional turns | 792.62 | 534.93 |
| Exploration: mean reversals | 509.57 | 294.59 |

Paired test outcomes: 37 known-stair cases changed from failure to success,
6 changed from success to failure; exploration gained 49 cases and lost 10.
There are 128 cases per condition on 32 held-out maps; this is one training
seed, and scenarios sharing a map are not independent replicates.

The original full-size validation set gives a more mixed picture: known-stair
success rose from 12.50% to 32.81%, but exploration only from 29.69% to 32.81%.
Those source validation numbers are from symbolic-ppo-fullsize-seed0.json with
the identical source checkpoint. The strong exploration test gain is therefore
not consistent across both held-out map groups. No checkpoint was selected
using those original full-size test outcomes.

Training and collection took 268.32s (4.47 minutes), excluding
evaluations. It collected 107,909 active environment decisions and used
1,366,040 valid supervised targets, including replayed examples.
These are **not PPO decisions** and do not indicate the sample efficiency of
learning from reward alone. Observed GPU memory usage was about 4.3 GB.

All remaining failures are timeouts; there are no enemies in these scenarios.
Repeated direction reversals persist. This demonstrates learnable native-scale
behavior and partial transfer from shorter routes, not reliable global route
planning. Curriculum and demonstration effects are not isolated by this run.

## Global-map intervention

`native_curriculum_ablation.py` repeats the original native test with the selected
checkpoint and zeroes only the 96-dimensional global encoded feature. Normal
rollouts reproduce the final success rates. Erasure changes:

- Known stairs: 31.25% -> 29.69% (40 -> 38 successes out of 128).
- Exploration: 56.25% -> 48.44% (72 -> 62 successes out of 128).

The global feature helps some exploration outcomes in this screen, but erasing
it has little net effect on known-stair success. That does not prove the branch
is unused: erasure is out of distribution, and gains/losses can cancel. It does
not supply evidence of reliable global goal routing either. The remaining
limitation is not resolved by the successful short-route stage.

Training, evaluations and the ablation are complete. Model/checkpoint files and
scene caches remain ignored; bounded JSON reports and source are versioned.
