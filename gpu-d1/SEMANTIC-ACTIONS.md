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

## First checkpoint (run still in progress)

Launched September 16, 2026, approximately 15:49 Halifax time. Background launcher
PID 1567351; worker PID 1567382. Process IDs are historical, not resumable handles.

| Policy | Clears / 1024 | Deaths | Timeouts |
|---|---|---|---|
| Untrained, sampled | 668 | 348 | 8 |
| 1,015,808 decisions, sampled | 911 | 104 | 9 |
| 1,015,808 decisions, greedy | 922 | 95 | 7 |
| Deterministic reference | 986 | 27 | 11 |

First checkpoint training time: 140.93 seconds, excluding validation; 2,482,782
underlying game turns. Sampled mean episode length 508.13 game turns / 207.76
policy decisions. Mean action selections: attack 137.75, explore 22.80, engage
41.24, wait 5.96, rest 0.02. Thus learning improves over the already capable
restricted-action initialization, but resting is almost absent at this early
checkpoint. Do not extrapolate this intermediate result to the final policy.

Initial completion estimate: 16:15–16:25 Halifax time, dependent on macro lengths.
The run remains bounded at approximately 10M decisions (whole PPO rollouts).

## Completed 10M result

Completed 10,027,008 policy decisions / 24,855,155 physical turns. Training-only
time 1,518.87 seconds (25.31 minutes); total runner time including validation and
checkpointing 1,754.16 seconds (29.24 minutes).

| Policy | Clears / 1024 | Deaths | Timeouts |
|---|---|---|---|
| 5M sampled | 948 | 66 | 10 |
| 10M sampled | 950 (92.77%) | 64 | 10 |
| 10M greedy | 961 (93.85%) | 57 | 6 |
| Deterministic reference | 986 (96.29%) | 27 | 11 |

Sampled REST usage remains two selections across 1,024 episodes; greedy REST
usage is zero. Mean sampled game turns 524.25, policy decisions 215.30, raw
shaped return 26.75, versus reference 681.00 / 260.46 / 27.30. The reference
rests 8.89 times per episode. A plateau is apparent on this validation panel:
doubling training from 5M to 10M adds only two sampled clears. This is one seed,
not evidence of an absolute performance ceiling. Discounting per physical turn
may discourage long recovery, but that causal explanation remains untested.

Final machine-readable summary: `results/semantic-actions-training.json`.
The autoregressive successor was cancelled while queued and did not train.

## Post-training deterministic REST override

Same 10M weights and 1,024 initial episodes. Draw the normal model action, then
replace it with REST whenever the existing REST mask permits it (damaged player,
regeneration, no visible awake enemy). All remaining actions stay policy-driven.
No retraining or hidden information. Both baseline replays exactly reproduce the
recorded clear/death/timeout counts. Greedy retains the original five-action argmax.

| Policy | Clears | Deaths | Timeouts | Mean game turns | Mean REST uses |
|---|---|---|---|---|---|
| Sampled baseline | 950 | 64 | 10 | 524.25 | 0.002 |
| Sampled + forced rest | 972 (94.92%) | 44 | 8 | 622.18 | 8.40 |
| Greedy baseline | 961 | 57 | 6 | 519.58 | 0 |
| Greedy + forced rest | 971 (94.82%) | 46 | 7 | 620.05 | 8.43 |
| Deterministic reference | 986 (96.29%) | 27 | 11 | 681.00 | 8.89 |

Sampled: 37 previously unsuccessful episodes become clears and 15 previously
successful ones cease clearing, net +22. Greedy: +18/-8, net +10. Same starting
scenarios do not imply identical future states/RNG consumption after intervention.
REST averages 96.26 physical turns sampled, 97.16 greedy. Raw shaped return rises
from 26.75 to 27.07 sampled, and 26.99 to 27.09 greedy.

The clear-count gap to the deterministic reference shrinks from 36 to 14 sampled,
and 25 to 15 greedy. Recovery neglect explains part of the observed performance
gap under this intervention; it does not establish why PPO avoided REST, nor
prove the remaining gap comes from any specific action. This is a single trained
seed on the reused validation panel.

Reproducer: `diagnostics/semantic-actions/rest_override.py`.
Results, checkpoint/library hashes and per-episode outcomes:
`results/semantic-actions-rest-override.json`.
