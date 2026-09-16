# Full-map seek-and-destroy baseline

2026-09-16. Evaluated the existing native heuristic on the same 1,024 validation episodes (32 held-out layouts × 32 placements, seed 900000), 24 enemies, 2048 physical-turn cap, no LOS, distance-based waking, full terrain/enemy knowledge, and the same stats and combat rules as the centered-map model.

The heuristic attacks the lowest-HP adjacent enemy. Otherwise it chooses the living enemy with the shortest traversable path distance and takes one step along a shortest path. It uses precomputed exact map distances. It does not avoid dangerous fights or plan multi-step combat. The rest variant first selects rest whenever the existing mask permits it: below full HP and no awake enemy within Chebyshev distance seven. Rest consumes ordinary physical turns.

| Policy | Clear % | Death % | Timeout % | Kills / 24 | Mean physical turns | Rest uses |
|---|---:|---:|---:|---:|---:|---:|
| Learned 10M, sampled | 14.26 | 43.95 | 41.80 | 13.29 | 1074 | 0.002 |
| Seek and destroy | 86.04 | 13.96 | 0.00 | 21.79 | 296 | 0.000 |
| Seek and destroy + rest | 91.89 | 8.11 | 0.00 | 22.63 | 401 | 7.451 |

Mean turns includes both deaths and clears; it is not a clear-only timing statistic. The heuristic variants have no timeouts. They clear 881/1,024 and 941/1,024 episodes respectively, versus 146/1,024 for the learned sampled policy. The rest variant averages 7.45 rest uses and 92.84 physical resting turns per episode.

This establishes that the task is largely solvable with the information already available to the model. Exact shortest-path computation and explicit attack/target-selection rules are supplied to the heuristic rather than learned. The result does not isolate navigation from combat selection as the model's bottleneck, does not establish optimality, and does not imply the remaining deaths are unavoidable. It also is not a comparison of learning efficiency: the hand-coded policy requires no training.

Both heuristic audits passed the same checks as the random-policy audit: every kill followed an attack on an adjacent enemy with at most four HP, and nonterminal kill-count changes matched disappearance of enemy HP records. Initial placements and simulation seeds match across policies, but subsequent combat RNG consumption differs with actions.

Reproduction:

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/centered-map-random/run.py --label seek-destroy --mode heuristic
gpu-d1/.venv/bin/python gpu-d1/diagnostics/centered-map-random/run.py --label seek-destroy-rest --mode heuristic_rest
```

Raw metrics: `results/centered-map-random-seek-destroy.json` and `results/centered-map-random-seek-destroy-rest.json`. Bulk trajectories remain ignored under `learning-runs/centered-map-random-audit/`.
