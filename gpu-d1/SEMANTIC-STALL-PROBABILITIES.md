# Greedy waiting probability audit

Replayed both 1M gamma=1 policies on the original 1,024 validation placements,
without interventions or retraining. Both reproduce exactly 0 clears, 16 deaths,
1,008 timeouts. A stall is at least 32 consecutive greedy WAIT decisions; all
1,008 timeout episodes contain a stall. Statistics below weight stalled decisions,
not episodes. Script: diagnostics/semantic-actions/stall_probabilities.py.
Detailed probabilities and example trajectories: results/semantic-stall-probabilities.json.

| Policy / situation | Share of stalled decisions | Mean WAIT probability | Mean progress probability |
|---|---:|---:|---:|
| Clear-only, no visible enemy | 66.83% | 55.96% | EXPLORE 44.04% |
| Clear-only, sleepers only | 33.17% | 69.81% | ENGAGE 30.19% |
| Shaped, sleepers only | 99.47% | 76.00% | ENGAGE 24.00% |
| Shaped, no visible enemy | 0.53% | 88.17% | EXPLORE 11.83% |

Every stalled decision has a valid progress action. None has an awake visible
enemy or adjacent attack available. REST is unavailable. All non-time observation
fields are unchanged from the preceding decision throughout these stalls.
Clear-only WAIT probability ranges from just over 50% to 85.87%; shaped WAIT
ranges from 56.21% to 96.18%, exceeding 90% on only 0.32% of stalled decisions.

Example clear-only episode 2: full HP, no enemies visible, turn 31 WAIT 58.61%
versus EXPLORE 41.39%. At turn 2047: WAIT 57.23%, EXPLORE 42.77%. It never moves.
Episode 3: a sleeping enemy at relative (7,-3), full HP; WAIT 74.73% versus ENGAGE
25.27% at turn 31, and 73.94% versus 26.06% at turn 2047.
The shaped policy on episode 3 increases WAIT from 68.24% to 83.51% as time passes.
These examples are the first four stalled episode IDs, not random samples.

This confirms the proposed argmax failure mechanism: substantial probability
remains on progress, but WAIT stays the largest probability, so greedy never
selects progress. Sampling can escape such states after a few decisions. It is
not an action-mask block or tactical waiting for an awake enemy to approach.
The diagnostic establishes behavior, not why optimization settled on these
probabilities; entropy, reward scale, value learning and temporal credit assignment
remain hypotheses rather than independently tested causes.
