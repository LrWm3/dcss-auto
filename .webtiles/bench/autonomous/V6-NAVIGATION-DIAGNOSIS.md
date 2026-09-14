# V6 navigation and diagnostic audit — 2026-09-12

Evidence: `artifacts/v6-navigation-audit-01/report.json`.
Reproduce with `diagnose_v6_navigation.py --run-dir RUN --output NEW_DIRECTORY`.
The audit uses held-out states only for diagnosis; it does not train on them or
modify any champion, candidate, or historical evaluation manifest.

## Fixed: diagnostic NaN

`policy_diagnostics` previously computed softmax, then log(probability). Very
confident finite logits can underflow probabilities to zero, making the KL
expression contain zero times infinity. The fix computes log-softmax directly
in double precision and rejects genuinely non-finite logits explicitly.
Regression checks cover extreme logits, ordinary KL agreement, and corrupt
inputs. Seven diagnostic/learner tests passed.

Recomputed on a reproducible 128-state retained-training sample:

| Candidate | KL from V0 | Decisions changed |
| --- | ---: | ---: |
| cycle 0 | 0.002618 | 1 / 128 |
| cycle 1 | 0.005304 | 1 / 128 |
| cycle 2 | 0.001964 | 1 / 128 |

Historical NaN manifests are preserved. Corrected diagnostics are in the new
report, using a new documented sample, not represented as the identical old
256-state diagnostic sample.

## Diagnosed: waiting is already broken in the bootstrap policy

The scripted teacher completed five demonstrations ending on D:2, D:3, D:2,
D:2 and D:3. V0 trained on 3,796 transitions for ten epochs; recorded cloning
loss fell from 0.453 to 0.135. Low training loss did not ensure rollout competence.

All 15 inspected V0 screen cutoff states chose WAIT at full health with no
visible enemies and an available teacher exploration move. In the first three,
WAIT probability was about 95–98%. Input interventions with unchanged weights:

| Intervention | Greedy MOVE | Greedy WAIT |
| --- | ---: | ---: |
| Original | 0 | 15 |
| Remove history | 13 | 2 |
| Replace recent actions with MOVE | 15 | 0 |
| Halve HP | 0 | 15 |
| Reset turn count | 0 | 15 |

This strongly supports a history shortcut: the policy depends on recent
actions and fails to leave repeated waiting when healing is complete. These
interventions diagnose sensitivity; synthetic history is not proposed as a
deployed policy and does not prove the exact training mechanism.

Two exact saved starting states were then replayed for 256 decisions each:

- Both original continuations executed WAIT 256 times, with unchanged score.
- Removing history in the first produced 93 moves, 19 melee actions and 144
  waits, increasing score 2→10. It ended on D:2 but issued no downstairs action;
  this must not be counted as demonstrated deliberate stair navigation.
- Removing history in the second produced four moves followed by 252 waits,
  leaving score at 4. History removal alone is not a complete repair.

The learner's measured behavior changes are very small. Resetting each rejected
candidate to this defective V0 also prevents those small weight changes from
accumulating across rejected cycles. That explains the operational behavior;
the audit does not establish that relaxing promotion would improve gameplay.

## Next repair to validate

Rework bootstrap training to discourage dependence on recent action identity
(for example, history dropout), and collect teacher corrections on the model's
own training-seed rollouts, particularly healing-to-exploration transitions.
Retain history about hazards/failed actions rather than assuming all memory
should be removed. Validate held-out rollout behavior before accepting a new
bootstrap as V0; currently the orchestrator accepts it after cloning regardless
of navigation competence. Compare both with and without history masking because
the second live continuation exposes an additional unresolved stall.

No navigation-policy change or new long training run was made during this
diagnostic task. The implemented repair is numerical diagnostic stability.
