# Semantic action learning, seed 0

Question: can PPO approach a deterministic controller when it chooses between
reliable behaviors instead of choosing directional move/attack commands?

Implementation: `branches/semantic-actions-v1`, isolated from previous experiments.

| Action | Execution | Availability |
|---|---|---|
| ATTACK | One attack against the weakest visible adjacent enemy; compass-order ties | Adjacent enemy |
| EXPLORE | Follow nearest observed frontier; continue through successive frontier targets until any enemy becomes visible, route blocks, no frontier remains, or episode ends | No visible enemy and a frontier step exists |
| ENGAGE | One observed-floor route step toward the closest reachable visible enemy | Next step exists and would not attack |
| WAIT | One ordinary game turn | Always |
| REST | Ordinary waits until full HP or an awake enemy becomes visible | Below full HP, regeneration enabled, no visible awake enemy |

No retreat action is provided. Sleepers can block EXPLORE but permit REST. Navigation
uses observed terrain; enemies are selected only when currently visible. Macros
execute normal physics, regeneration, wake checks, and rewards on every game turn.

Training: 10M policy decisions, seed 0, 24 enemies, 2048 **physical game turns** per
episode, 256 training layouts with the existing one-third clumped placement mix.
Validation: the existing 32 layouts × 32 placements, sampled and greedy policy,
at initialization and approximately 1M, 3M, 5M, 10M decisions. Same 999 observations,
15×15 LOS, wall-blocked vision/waking, sleep status, seen-floor count, frontier cue,
and exact-D4 averaged two-layer 128-wide network. Five invariant action logits.

Rewards: +1 kill, +3 clear, -4 death, -0.001 per game turn, +0.002 newly revealed
floor. Macros return the sum for reporting; PPO receives intra-macro discounted
rewards and bootstraps with gamma^duration (gamma=0.99 per game turn). GAE lambda
is 0.95 per policy decision. This is a duration-aware credit assignment choice,
not the same objective as counting a whole macro as one discounted turn.

The older rest/sleep policy used a policy-decision deadline and blocked rest for
visible sleepers. Therefore its historic scores are context, not a matched
control. Execution heuristics, action restrictions, temporal abstraction and
credit assignment all change here. Success would show that learning behavior
selection works, not establish directional-logit interference as the sole cause
of previous failures. This reused validation panel is not an untouched test set.

## Deterministic reference

Priority: ATTACK; otherwise REST if available; otherwise WAIT for visible awake
enemies; otherwise ENGAGE; otherwise EXPLORE; otherwise WAIT. Same environment,
primitives, observations available to the controller, and physical deadline.

| Clears | Deaths | Timeouts | Mean game turns | Mean policy decisions |
|---|---|---|---|---|
| 986/1024 (96.29%) | 27 | 11 | 681.00 | 260.46 |

Mean kills 23.34; raw shaped return 27.30. Per-episode results and action counts:
`results/semantic-actions-reference.json`.

## Running and artifacts

Use `gpu-d1/.venv/bin/python` for these scripts:

```
branches/semantic-actions-v1/scripts/assets.py
branches/semantic-actions-v1/scripts/preflight.py
branches/semantic-actions-v1/scripts/evaluate_reference.py
branches/semantic-actions-v1/scripts/run_experiment.py
```

Paths above are relative to gpu-d1. Preflight checks action semantics, interruption,
exact physical deadline, macro equivalence to primitive turns, discounted rewards,
D4 invariance, inactive-world freezing, a small PPO run and checkpoint resume.

Training artifacts and logs live under ignored `learning-runs/semantic-actions/`.
The runner retains latest/best checkpoints and compact evaluation snapshots,
with a 2 GiB disk budget and 10 GiB minimum free space. It writes training time,
underlying game turns, action counts, rest/explore durations, clear/death/timeout
rates, and sampled/greedy validation. Completion writes the compact tracked result
to `results/semantic-actions-training.json`. Training status remains in
`learning-runs/semantic-actions/status.json`.
