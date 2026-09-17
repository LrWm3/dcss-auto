# Remembered-grid navigation: completed first demonstration

A learned local/global spatial encoder can navigate these unfamiliar synthetic floors without frontier arrows, stair arrows, route distances, or runtime controller actions. This is a supervised navigation result, not an ordinary-D1 or PPO result.

All arms trained for 12,000 optimizer updates (3,072,000 sampled supervised examples). Spatial-model checkpoints were selected using validation; the simple CNN uses its final checkpoint. Training used behavior cloning plus corrective labels on mixed student/teacher trajectories. The policy starts from scratch.

## Main held-out results

Greedy exit percentages. Known stairs and exploration each contain 256 episodes on the same 64 held-out mazes (four placements per map). Pressure contains 32 separately generated junctions. The budget is 256 physical turns including setup history.

| Representation | Known stairs | Explore to stairs | Threat backtracking |
|---|---:|---:|---:|
| Local crop only | 11.33% | 37.11% | 96.88% |
| Local + simple global CNN | 35.16% | 75.39% | 100.00% |
| Local + spatial global terrain | 92.19% | 90.23% | 100.00% |
| Local + spatial global terrain + enemy memory | 83.98% | 92.19% | 100.00% |

With sampled actions, the full spatial policy exits in **91.80%** of known-stair cases and **96.48%** of exploration cases. The untrained spatial policy exited in none of the validation episodes.

The pressure suite is too easy to establish the value of last-seen-enemy memory: the local-only and terrain-only controls also solve it. Success in those fixtures must not be interpreted as proof that the policy remembered and reasoned about the monster. All pressure exits should be read alongside the recorded wake/kill statistics.

## Paired distant-goal diagnostic

The local crop, player statistics, action mask and walked path are identical within each pair. Only the distant remembered staircase locations differ. Both possible exits are outside the local crop. Initial direction, rather than eventual exit, tests whether the policy uses that global information.

| Representation | Correct initial direction | Both members correct |
|---|---:|---:|
| Local crop only | 50.00% | 0 / 24 |
| Local + simple global CNN | 85.42% | 17 / 24 |
| Local + spatial global terrain | 100.00% | 24 / 24 |
| Local + spatial global terrain + enemy memory | 100.00% | 24 / 24 |

Zeroing the trained full policy's global features gives 50.00% correct initial directions and 0/24 complete pairs. This is an out-of-distribution intervention; the separately trained local-only control is the cleaner comparison.

## Larger/longer layouts

These use 6x6 maze construction nodes rather than the 4x4/5x5 training layouts, with 128 episodes per navigation condition on 32 maps. Pressure backtracks are 12/14 tiles rather than 4/6/8/10. The deadline is increased to 512 turns so the history walk plus return is feasible; this is not a matched-deadline comparison.

| Representation | Known stairs, greedy | Exploration, greedy | Known stairs, sampled | Exploration, sampled |
|---|---:|---:|---:|---:|
| Local crop only | 3.12% | 17.19% | 32.03% | 10.94% |
| Local + simple global CNN | 6.25% | 39.06% | 18.75% | 50.00% |
| Local + spatial global terrain | 53.91% | 67.19% | 69.53% | 82.03% |
| Local + spatial global terrain + enemy memory | 38.28% | 67.19% | 67.19% | 79.69% |

The observation-limited teacher reaches every exit in the recorded validation, test, and long panels. Remaining model failures therefore have a demonstrated feasible route under the same budget. This does not show that every arbitrary Crawl floor is solvable.

## Training cost

| Representation | Rollout decisions | Measured training/collection time | Selected update | Parameters |
|---|---:|---:|---:|---:|
| Local crop only | 1,258,286 | 111.3 s | 12,000 | 353,363 |
| Local + simple global CNN | 1,094,528 | 154.7 s | 12,000 | 545,627 |
| Local + spatial global terrain | 896,077 | 348.6 s | 12,000 | 353,363 |
| Local + spatial global terrain + enemy memory | 888,625 | 347.9 s | 12,000 | 353,363 |

Times include teacher-label generation and optimizer work, and exclude validation rollouts. The initial CNN/U-net measurements also include validation environment-construction overhead, fixed in subsequent control runs. Compilation, fixture generation, final evaluation and implementation time are additional. Rollout decisions exclude scripted reset histories and are not autonomous PPO decisions.

## Interpretation and limits

- This establishes useful map-conditioned navigation on unseen layouts within these procedural families. The stronger spatial encoder outperforms simply flattening a coarse global CNN summary.
- The distant-goal pairs distinguish using global information from a fixed local movement habit. Consult the measured table rather than assuming every policy passes.
- Longer-route performance measures a real remaining generalization limit; the representation is not a guaranteed pathfinding algorithm.
- One training seed, fixed player stats, at most one dangerous sleeper, small synthetic floors. No ordinary-floor combat retention, full 80x70 Crawl map generalization, or PPO improvement is claimed.
- Enemy-memory benefits remain unproven by this easy pressure suite. It needs situations where histories require different useful decisions, rather than a universally safe backtracking response.

## Checks and artifacts

- 384 distinct terrain arrays across the four splits; 667 CPU/CUDA transition comparisons; 1680 hidden-state/terrain checks; 6 out-of-view memory pairs.
- The original automatic-reset behavior and legacy semantic checks pass without the experiment-only compile flag.
- [Exact measurements](../../results/remembered-grid.json), [illustrative trajectories](../../results/remembered-grid-examples.svg), [implementation and reproduction](README.md).
- Raw models/maps remain in the ignored, bounded `learning-runs/remembered-grid` directory. Original experiments and unrelated result files are untouched.
