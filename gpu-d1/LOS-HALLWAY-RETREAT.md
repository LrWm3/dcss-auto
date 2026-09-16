# Hallway retreat with seek-and-destroy and rest

2026-09-16. Four deterministic heuristic arms, each on the same 1,024 initial validation episodes (32 maps × 32 placements, seed 900000). Uses the original 15×15 wall-blocked LOS / visible sleep-status simulator, 24 enemies, LOS-gated waking, and 2048 **policy decisions**. Rest runs ordinary physical turns until full or interrupted, and is available only below full HP with no visible enemy (including sleepers). No training was performed.

## Exact retreat rule

- Trigger when at least two currently visible enemies are awake. Sleeping or hidden enemies do not count.
- A hallway is a known floor tile with exactly two opposite known floor neighbors and six known wall neighbors. Horizontal, vertical and both diagonal axes qualify. Unknown tiles never count as walls.
- Choose the nearest reachable qualifying hallway by shortest path through remembered observed floor. The destination displacement and first step must both have negative dot product with the vector toward the visible awake enemies’ centroid. Equal-distance candidates use tile-index order. If already in a qualifying hallway, hold the current tile.
- Commit to that destination. Recompute the route through observed floor as knowledge changes; route planning ignores enemy occupancy so a blocking enemy causes cancellation, rather than a detour around it.
- If a visible enemy occupies the next step, abort retreat and resume normal policy immediately. A failed movement into known static floor also infers an unseen enemy blocker after that step and aborts. No true occupancy lookup is used. Other adjacent enemies do not cancel a retreat if they are not blocking the next step.
- On arrival, wait until an enemy becomes adjacent, then resume normal combat. The retreat opportunity is spent for the current visible encounter after either combat resumption or an abort.
- Interpret “all enemies are gone” as **no enemy currently visible**: this resets the lockout and also cancels an unfinished retreat/hold. It does not wait for a hidden enemy count to reach zero. If no qualifying hallway exists, use normal policy and allow reconsideration later.

Ordinary behavior is either privileged nearest-enemy pursuit or LOS-only visible-enemy pursuit / nearest-frontier exploration. Both include rest. **Retreat itself uses only observed terrain and visible enemy/sleep records in both arms.** Its API has no hidden map, enemy state or full-map distance pointer. The privileged arm retains hidden knowledge only in its ordinary pursuit policy.

## Results

| Policy | Clear % | Death % | Timeout % | Mean physical turns | Clear-only physical turns |
|---|---:|---:|---:|---:|---:|
| privileged-control | 93.55 | 6.45 | 0.00 | 426.2 | 447.7 |
| privileged-retreat | 96.97 | 3.03 | 0.00 | 460.1 | 472.9 |
| local-control | 92.68 | 6.54 | 0.78 | 609.3 | 630.5 |
| local-retreat | 96.29 | 2.83 | 0.88 | 651.7 | 656.9 |

The controls exactly reproduced the previous matching baselines for clear/death/timeout rates, kills, physical turns and rest uses. Privileged retreat clears 993/1,024 versus 958/1,024; LOS-only retreat clears 986/1,024 versus 949/1,024. Deaths fall from 66 to 31 and from 67 to 29 respectively. No timeouts occur in the privileged arms; local timeouts change from eight to nine.

| Retreat metric, per episode unless stated | Privileged base | LOS-only base |
|---|---:|---:|
| Episodes with retreat | 94.1% | 95.6% |
| starts | 3.635 | 3.997 |
| arrivals | 3.183 | 3.424 |
| retreat_steps | 22.552 | 24.555 |
| hold_waits | 1.696 | 1.866 |
| enemy_blocks | 0.039 | 0.053 |
| inferred_enemy_blocks | 0.000 | 0.000 |
| route_aborts | 0.000 | 0.000 |

No deaths occurred on retreat movement actions or hallway-holding waits in this panel. That does not prove these actions are universally safe. Waiting averaged fewer than two turns per episode: enemies frequently reach adjacency by arrival, so the rule mostly changes the combat location. This is an interpretation of the counters, not an isolated ablation of waiting versus retreating.

## Paired outcomes

| Starting episode outcome | Privileged base | LOS-only base |
|---|---:|---:|---:|
| both_clear | 957 | 943 |
| retreat_only_clear | 36 | 43 |
| control_only_clear | 1 | 6 |
| neither_clear | 30 | 32 |

The same starting placement and seed do not preserve the same subsequent combat RNG draws after actions diverge. These comparisons show a strong improvement on this validation panel, not that every remaining death is avoidable, or that the rule is optimal. The panel has been reused during development; no untouched-test claim is made.

## Checks and reproduction

Synthetic tests passed for four rotated room-to-hall routes, all four hallway axes including diagonals, awake-only triggering, unknown-wall rejection, rejecting a hallway toward enemies, retreat despite a nonblocking adjacent foe, arrival/wait/adjacency transition, visible and inferred blocking, lockout and visibility reset, rest availability and inactive-state freezing. Every evaluation action passed the original legal mask. Original simulator library hashes were verified.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/test_retreat.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/run_retreat.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/report_retreat.py
```

Raw metrics, paired outcomes, per-episode events and source/library hashes: `results/los-hallway-retreat.json`. Compiled helper libraries remain under ignored `learning-runs/seek-destroy-los-assets/`.
