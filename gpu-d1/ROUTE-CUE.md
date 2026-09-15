# Frontier route-cue ablation

**The original run is invalid as a test of route guidance.** Its cue compared
neighbor distances from the player against the target distance, which does
not identify a step toward the target. The negative conclusion previously
reported from that run is withdrawn. Original artifacts are retained for audit.

The corrected implementation backtracks from the selected frontier along
decreasing player-rooted BFS distances until it reaches the first step.
The corrected 10M seed-0 run uses a fresh output directory:
`learning-runs/ring-route-cue-corrected-seed0/`.

The route-cue variant adds eight one-hot inputs after the known-frontier
observation. They identify the first step on a shortest path through observed
floor from the player to the selected nearest frontier anchor. Unknown terrain
is never used to compute the cue. If the player is already at the anchor, or no
known-floor route exists, all eight cue inputs are zero. The eight positions
use the existing action order: north, east, south, west, northeast, southeast,
southwest, northwest.

Seed 0 was trained for 10,000,000 requested decisions with the same 40 enemies,
1024-turn horizon, 256 training maps, rewards, PPO settings, and validation
protocol as the known-frontier run. The update boundary produced 10,027,008
decisions.

| Model | Training seconds | Decisions/second | Sampled clears | Sampled kills | Greedy clears | Greedy kills |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Known frontier, seed 0 | 155.6 | 64,434 | 4.88% | 15.69 | 0.39% | 10.94 |
| INVALID original route cue, seed 0 | 157.4 | 63,688 | 4.30% | 15.52 | 0% | 10.15 |

These original route-cue scores cannot establish whether correct route
guidance helps. A successful smoke test checked execution, not cue semantics.
The corrected version has explicit semantic tests for a wall detour requiring
an initial move away from the target, an unseen shortcut, a newly observed
direct route, an adjacent target, arrival, an unreachable target, and no target.

The run passed the GPU smoke test before the 10M run. Outputs are in
`learning-runs/ring-route-cue-seed0/`; the compact result is in
`runs/route_cue-seed0/result.json` and the evaluation curve is in
`runs/route_cue-seed0/curve.json`.

Reproduce with:

```sh
gpu-d1/.venv/bin/python gpu-d1/scripts/run_ring_ablations.py \
  --variants route_cue --steps 10000000 \
  --output gpu-d1/learning-runs/ring-route-cue-corrected-seed0
```
