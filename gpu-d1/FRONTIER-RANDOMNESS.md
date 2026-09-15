# Frontier action randomness evaluation

Evaluated the saved 10M known-frontier policies for training seeds 0, 1 and 2.
No training was performed. Evaluation plus trajectory diagnostics took
163.24 seconds; total measured runtime including loading was 167.85 seconds.

Each condition used 1,024 episodes per model: 32 episodes on each of the same
32 validation layouts. Initial environment and action RNG seed was 910777,
different from the training-time validation seed. Only each world's first
episode counted. This is additional validation, not an untouched test split.
Six temperatures across three models give 18,432 evaluated episodes.

Temperature 0 chooses the most likely legal action. Positive temperatures
divide the policy's masked logits by temperature before sampling. Temperature
1 reproduces normal sampling; smaller values favor the preferred action.

| Temperature | Clears | Kills | Deaths | Timeouts | Floor seen | Stall windows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 (greedy) | 0.03% | 10.35 | 51.17% | 48.80% | 23.69% | 38.84% |
| 0.25 | 1.30% | 14.49 | 60.71% | 37.99% | 33.94% | 12.51% |
| 0.5 | 3.84% | 16.32 | 62.24% | 33.92% | 38.80% | 3.02% |
| 1 | 3.97% | 16.24 | 67.58% | 28.45% | 39.47% | 0.42% |
| 1.5 | 2.28% | 15.17 | 71.71% | 26.01% | 37.39% | 0.18% |
| 2 | 0.75% | 13.90 | 74.87% | 24.38% | 34.78% | 0.07% |

Rows average the three equally sized seed evaluations. Floor seen is the
fraction of a layout's floor cells exposed by pre-action 9x9 observations.
The final post-action observation is excluded because the simulator auto-resets.
This can omit the final move's newly exposed tiles. Unique visited positions
use the same pre-action convention. Diagnostic map-cell counts only normalize
reported coverage and are never given to the policy.

A stall window means the last 32 pre-action positions contain at most two
distinct squares, with no adjacent live monster anywhere in that window.
The reported value averages each episode's fraction of turns satisfying this
condition; overlapping windows count separately. This detects stationary and
two-square stalls, not every possible movement loop. Quiet reversals in the
JSON count returns to the position two turns ago after leaving it, without an
adjacent live monster at the current observation.

Among timed-out episodes, the stall-window fraction was 71.40% for greedy
play and 1.33% for ordinary sampling (mean of per-seed timeout metrics).
This gives direct evidence that sampling helps escape short navigation loops.
It does not establish whether their underlying cause is observation ambiguity,
target switching, insufficient memory, or the learned action preferences.

More randomness is not monotonically better. Temperatures 0.5 and 1 achieved
similar clears; the preferred one varied across seeds. Temperature 0.5 had
fewer deaths but more timeouts. Higher death rates may reflect more enemy
encounters as well as worse decisions; this evaluation does not separate those
causes. Extra randomness beyond 1 reduced clears despite eliminating stalls.

A useful next diagnostic is conditional randomness: use temperature 0.5 by
default and temporarily increase it after a quiet navigation stall, compared
against the fixed 0.5 and 1 controls. This would test whether loop escape can
be preserved with less randomness elsewhere. That follow-up has not been run.

Reproduce with:

```sh
gpu-d1/.venv/bin/python gpu-d1/scripts/evaluate_frontier_randomness.py
```

Detailed per-seed, per-map, and per-outcome metrics plus checkpoint/library
hashes are in `results/frontier-randomness/summary.json`. The evaluator uses
the original suite libraries and does not alter their source manifests or
checkpoints. JSON output uses the bounded atomic storage helper.
