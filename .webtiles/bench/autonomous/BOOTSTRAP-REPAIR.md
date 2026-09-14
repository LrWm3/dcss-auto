# V6 bootstrap repair

V6's original bootstrap repeatedly chose WAIT on its own states despite good
teacher-data accuracy. This bounded bootstrap repair precedes RL for new V6 runs.
Existing champions are not silently replaced.

The repair collects three fresh teacher demonstrations, then up to three rounds
of teacher labels on three greedy neural-policy rollouts. Training uses separate
seed namespaces from validation. It combines these corrections with existing
training labels, stratifies by teacher action, and masks recent action identity
and direction on half the training examples. History of hazards, HP changes,
failed actions, and last-seen enemies remains available. No runtime movement or
berserk rule is added to the neural policy.

Each candidate must complete five development-validation games without missing
scores/errors, deliberately take downstairs in at least two games, and have at
most one decision-capped game dominated (>80%) by WAIT. A shaft alone cannot
qualify as deliberate descent. This is a basic bootstrap gate, not proof of
full-game improvement or champion promotion. These repeatedly inspected seeds
are development validation, not an untouched final test.

The original V0 is evaluated on the same validation seeds for comparison.
Checkpoints, teacher trajectories, per-game results, training metrics, and gate
results are retained. Completed episodes are reused after interruption; partial
training trajectories are quarantined and excluded from fitting.

Run an isolated repair (does not start RL or modify the source champion):

```bash
.webtiles/bench/tactical/.rl-venv/bin/python \
  .webtiles/bench/autonomous/repair_structured_bootstrap.py \
  --source-run .webtiles/bench/autonomous/artifacts/foundation-general-training-v6 \
  --output .webtiles/bench/autonomous/artifacts/v6-bootstrap-repair-01
```

Inspect `status.json`, `baseline/results.json`, and each round's `training.json`,
`validation/results.json`, and `gate.json`. Three failed rounds stop with
`needs_review`; no RL is launched. The existing low-space guard applies.

## Follow-up diagnosis

The first repair failed all three navigation gates. Recomputing teacher labels
on 1,024 sampled training observations found no label mismatches. On the latest
correction sample, the teacher recommended MOVE in 251/256 states, but the last
repair chose WAIT in 250 of those states. See `v6-bootstrap-repair-01/label-audit.json`.

A training-only 512-example probe demonstrated that the representation can fit
these corrections: longer fitting at learning rate 0.0003 achieved 96.7% ordinary
input exact-action accuracy from the existing model and 97.9% from a fresh model.
These are fitting results, not held-out gameplay results. The warm model also
lost many appropriate healing waits. Both models receive independent live
development validation; neither is automatically promoted.

Two pipeline changes follow from this diagnosis:

- Report normal-input and history-masked fitting accuracy separately, including
  per-teacher-action-kind counts. Mixed training accuracy concealed the gap.
- Reserve up to eight examples of each observed teacher action kind during
  replay sampling, then fill the remaining budget with random coverage. The
  original 256-example demonstration sample omitted every stairs example.

Future repair rounds use 12 epochs at learning rate 0.0003, still subject to the
unchanged live navigation gate. Historical checkpoints/results remain unchanged.
The small probes in `v6-fit-probe-01` predate the rare-action sampling fix and
must not be treated as complete bootstrap datasets.
