# V2 PPO on the 388-map D1 corpus: 10M decisions

This run tests the full-corpus loader and multi-map training setup. PPO trained on the 256-map training split and was evaluated on the held-out 32-map validation split. The 100-map test split was not used.

Audit correction: this used the older v2 task, **not** the recent ring/frontier
task. It has eight enemies, a 512-turn limit, four fixed monster stat roles,
randomized player stats, a 250-float observation, globally revealed enemy
positions, and no exploration reward or remembered terrain. It cannot isolate
the effect of adding layouts to the recent 40-enemy, 1024-turn runs.

Command:

```bash
gpu-d1/.venv/bin/python -u gpu-d1/scripts/train_v2.py \
  --train-corpus gpu-d1/fixtures/d1-corpus-388/train \
  --eval-corpus gpu-d1/fixtures/d1-corpus-388/validation \
  --enemies 8 --steps 10000000 --seeds 0,1,2 \
  --output gpu-d1/learning-runs/v2-d1-388-10m
```

The requested 10M target produced 10,027,008 decisions per seed (the next complete PPO rollout). Training ran at 268–272k decisions/s.

| Policy / seed | Clear rate | Enemies killed | Mean return |
| --- | ---: | ---: | ---: |
| Sampled, 0 | 6.54% | 3.83 / 8 | 3.42 |
| Sampled, 1 | 1.66% | 3.29 / 8 | 2.74 |
| Sampled, 2 | 3.13% | 3.29 / 8 | 2.79 |
| Greedy, 0 | 1.66% | 2.43 / 8 | 1.87 |
| Greedy, 1 | 0.88% | 2.54 / 8 | 1.95 |
| Greedy, 2 | 1.27% | 2.46 / 8 | 1.89 |

For reference, on the same validation episodes the fixed baselines were:

| Baseline | Clear rate | Enemies killed |
| --- | ---: | ---: |
| Wait | 0.00% | 0.00 / 8 |
| Random | 0.00% | 1.00 / 8 |
| Pursuit | 72.85% | 7.07 / 8 |

Pursuit uses shortest paths through the full true map; the policy gets only a
local 9x9 terrain window. This is an information-advantaged reference, not a
matched-information baseline or an upper bound on achievable performance.

The learned policy is above wait/random and improves steadily over the run, but remains far below the hand-coded pursuit baseline. Seed variance is material at this budget, so this is evidence that the full-corpus setup learns a weak combat policy, not evidence of robust floor-generalizing play yet.

Artifacts: [`config.json`](learning-runs/v2-d1-388-10m/config.json), [`baselines.jsonl`](learning-runs/v2-d1-388-10m/baselines.jsonl), and the per-seed [`curve.jsonl`](learning-runs/v2-d1-388-10m/seed-0/curve.jsonl), [`curve.jsonl`](learning-runs/v2-d1-388-10m/seed-1/curve.jsonl), and [`curve.jsonl`](learning-runs/v2-d1-388-10m/seed-2/curve.jsonl).

## Audit and fresh evaluation

The three recorded source hashes still match the source files. All splits have
their expected counts and no duplicate floor masks within or across splits
(256/32/100). This checks geometry as well as full binary hashes. Reading test
files for this integrity check did not evaluate policies on them.

Fresh sampled evaluations used 1,024 episodes per split and training seed,
environment/action seed 910000, and the exact recorded task settings:

| Training seed | Train clear | Validation clear | Train kills | Validation kills |
| --- | ---: | ---: | ---: | ---: |
| 0 | 6.54% | 5.08% | 3.86 | 3.73 |
| 1 | 2.64% | 2.15% | 3.40 | 3.38 |
| 2 | 3.91% | 3.52% | 3.55 | 3.43 |
| Mean | 4.36% | 3.58% | 3.60 | 3.51 |

The small observed gap and low training performance suggest task learning is
currently a larger limitation than floor overfitting. This is not an equivalence
test: floor difficulty differs between splits, and evaluation samples maps
randomly. Roughly 76–83% of these episodes time out. Aggregate results do not
identify whether navigation, engagement, or waiting causes those timeouts.

Raw audit results: [audit-fresh-train-validation.json](learning-runs/v2-d1-388-10m/audit-fresh-train-validation.json).
Next experiment: [controlled ring generalization design](EXPERIMENT-RING-GENERALIZATION.md).
