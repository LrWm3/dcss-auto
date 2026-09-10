# Cost-aware berserk gate — 2026-09-10

This is the first test of penalizing unnecessary berserk use. The gate still
chooses at the actual first two-tile state, but its paired targets are utilities:

```text
recovered_quiet = +100
budget timeout  =    0
death           = -100
berserk use     =   -2 once per encounter
```

Thus, when near and never both recover, never is preferred. A berserk that changes
death or timeout into recovery remains overwhelmingly worthwhile.

The model was trained on the original 72 paired variants plus the first fresh
36-case batch (107 usable decision states). It was evaluated on the held-out third
batch of 36 paired cases.

| Policy | Recovered | Died | Budget | Berserk uses |
| --- | ---: | ---: | ---: | ---: |
| Never control | 25 | 11 | 0 | 0 |
| Near control | 35 | 0 | 1 | 36 |
| Cost-aware gate | 34 | 1 | 1 | 24 |

The gate saved 12 berserk activations but lost one recovery: it chose never on a
case where near recovered and never died. Its total utility was 3,252 versus
3,428 for always-near under the same cost. The one timeout was shared by both
policies. Action auditing passed: 36 episodes, 34 recoveries, one death and one
budget truncation, with no harness errors or no-turn stalls.

The result means the penalty is behaving as intended mechanically, but the current
feature/tree model cannot safely identify when a berserk is unnecessary. Changing
the cost from 0.1 through 8 did not change its third-batch choices; the learned
tree partitions, rather than the small tie-break cost, caused the withholding.

The safe rule remains lexicographic: preserve recovery first, then minimize
berserk use only among policies with equivalent held-out outcome evidence. A
future cost-aware learner should require a confidence margin or repeated
counterfactual wins before withholding; raw utility regression is too willing to
trade one death for several saved activations.

No RC deployment. The run is retained as a negative regression test.
