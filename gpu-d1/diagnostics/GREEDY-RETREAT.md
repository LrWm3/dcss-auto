# Does greedy selection fix uncertain retreat decisions?

No general improvement. These are the original, unaugmented seed-0 30M models;
no retraining. Greedy means taking the highest-probability legal action at every
step, not selecting the action with greatest immediate reward or using search.
Combat randomness remains. Matched initial states, 512 combat seeds per condition,
two rosters, three player HP values, and four rotations are unchanged.

Natural clear rates for the tougher six-enemy roster, player HP 12/18, pooled
across four rotations:

| Geometry | Original sampled | Original greedy | Clumped sampled | Clumped greedy |
|---|---:|---:|---:|---:|
| Three-step straight hallway | 7.42% | 0.49% | 51.81% | 54.54% |
| Four-step diagonal pocket | 17.53% | 21.78% | 30.57% | 20.46% |
| Six-step diagonal pocket | 5.96% | 0.10% | 19.29% | 19.29% |

Six-step pocket arrival falls from 11.52% to 0.20% for original, and from 27.44%
to 25.10% for clumped. The clumped model's unchanged aggregate clear rate conceals
more concentrated success: greedy clear rates by pocket direction SE/SW/NW/NE
are 0%, 76.76%, 0.39%, 0%. Sampled rates were 15.43%, 60.74%, 0.78%, 0.20%.
Neither model's most likely initial action is the direct diagonal retreat in any
of these four six-step initial states; other paths remain possible.

Supplying just the first retreat step improves six-step greedy clears to 30.08%
original and 41.80% clumped. Supplying the whole retreat gives 43.90% and 62.65%,
compared with 63.57% and 63.48% under sampled defense. Under the full forced route,
greedy original clears 0% in the NW pocket and greedy clumped clears 0% in NE.
Waiting with an adjacent enemy is 67.67% original and 52.66% clumped across contact
turns in that forced-route condition, versus sampled 34.55% and 38.76%.

Some forced-retreat greedy runs are still alive/unresolved at the diagnostic's
256-action cap (full-route tough12: original 3.86%, clumped 3.17%). These are not
native 2048-turn timeouts, and do not demonstrate permanent waiting. Natural
runs in the headline tough12 cases all resolve. Do not report all failures in
other conditions as deaths.

Interpretation: the retreat weakness is not simply randomness disrupting an
otherwise correct most-likely plan. Greedy selection often reinforces poor
preferences; sampling sometimes allows an alternative route/action. This does
not mean sampling is universally better: clumped hallway and original four-step
pocket improve under greedy. Single training seed, synthetic geometry; no claim
about greedy superiority on ordinary maps.

Scripted control results, checkpoint hashes and initial policy probabilities
match stored sampled references exactly. Outcome accounting (win/death/unresolved)
passes for every condition. Rotations share combat seeds and are not independent
training replicates. Distances 4 and 6 also differ in room size.

Reproduce:

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/distant-pocket/run.py --distance 6 --greedy
gpu-d1/.venv/bin/python gpu-d1/diagnostics/distant-pocket/run.py --distance 4 --greedy
gpu-d1/.venv/bin/python gpu-d1/diagnostics/hallway-six/run.py --greedy
gpu-d1/.venv/bin/python gpu-d1/diagnostics/greedy_retreat_report.py
```

Raw outputs use `*-retreat-greedy.json`, without overwriting sampled results.
Summary: `results/greedy-retreat-comparison.json`.
