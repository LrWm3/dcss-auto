# Sleeping-threat bypass practice and waiting diagnosis

Launched 2026-09-17. One seed, two matched continuations from the anonymous-power
5,000,192-decision checkpoint. Checkpoints at500,224 and1,000,448 additional
decisions per arm. No production observation, action, reward, or transition
changes. Experiment outputs are isolated under `learning-runs/d1-sleeper-bypass`.

## Why the policy waits

Inspected the27 saved full-HP WAIT stalls from the previous diagnostic, selected
as the first three per player profile after64 consecutive waits. These are a
selected sample, not all timeout episodes.

- All27 have a legal next MOVE in the existing frontier direction.
- In25/27, that next step wakes the visible sleeper; the selected frontier route
  enters its wake zone. This is a danger conflict, not a wall/occupancy mask.
- All27 have at least one legal move that does not wake that sleeper.
- In26/27, another frontier is reachable over already-known floor without waking
  it. The alternative route is2–15 steps long;24 use a different first direction.
- In26/27, an oracle using full terrain finds an exit route avoiding that sleeper.
  This last check ignores other enemies: it is not a whole-floor safety proof.

Paired observation interventions, leaving the real state and action mask intact:

| Observation | Mean WAIT probability | Greedy WAIT states |
| --- | ---: | ---: |
| Original |77.95%|27/27|
| Hide visible enemy information |0.023%|0/27|
| Only enemy damage cap changed to1 |37.36%|10/27|
| Change enemy sleep observation to awake |99.53%|27/27|
| Zero enemy sleep-status observation |98.94%|27/27|
| Player changed to30HP / damage cap6 |87.02%|27/27|
| Zero frontier fields |70.15%|22/27|
| Redirect frontier to safe alternative, when available |69.95%|21/27|

The enemy observation causally drives waiting in these states. The frontier
usually points into immediate danger, but correcting that cue alone does not
reliably produce movement. The stronger-player result also warns against
interpreting this as a consistently calibrated risk model. Removing the enemy
is an artificial observation intervention, not a safe deployment strategy.
The sleep flag does affect probabilities: it lowers waiting compared with the
awake counterfactual. Thus this is not simply complete blindness to sleep state;
the effect is insufficient to change the greedy action in these selected stalls.

The safe-frontier replacement updates target, distance, unknown-neighbor fields,
and next-step direction together. It uses only known terrain and exact visible
sleeper wake LOS. All other observation channels and legal actions stay fixed.
The one state without a reachable safe frontier is unchanged in that variant.

## Training experiment

- **Control:** ordinary varied-stat floor training.
- **Practice:** on40% of episode resets, attempt to substitute a verified bypass
  encounter on that same training map and initial player position. About65% of
  attempted placements passed the initial geometry screen, giving roughly26%
  practice starts; actual completed episode counts are logged separately.
- A practice encounter has one visible sleeping enemy seven tiles away. The
  ordinary frontier route enters its wake zone, a safe known frontier exists,
  and at least one initially hidden stair is reachable without waking it.
- Remove other enemies only in practice episodes. Keep the same six calibrated
  stat templates and nine player profiles. Start at half or full player HP.
- Stairs remain at their ordinary reset locations; no stair guide exists until
  discovery. The generator's full-terrain feasibility check is not an input.
- Ordinary episodes retain24 enemies, one-third clumped placement,2048 physical
  turns,15x15 LOS, LOS wake, REST, frontier/stair cues, and anonymous enemies.
- Reward remains +1 exit and -0.00001 per physical turn; no avoidance labels,
  demonstration actions, special practice reward, or forced policy decisions.
- Reuse audited PPO and replay anchors. Both arms initialize model and optimizer
  identically from5M weights with a fresh Adam optimizer; both retain the same navigation replay and source-policy nominal
  replay targets, now anchored to the common5M starting checkpoint.

This is a curriculum pilot, not an isolation of every mechanism. It adds easier
single-enemy episodes as well as bypass geometry. Success would justify a later
matched single-enemy curriculum control. Equal policy decisions are not equal
physical turns or completed episodes; report all available timing/turn counts.

## Validation and checks

Generation depends on geometry, never policy success. Train/validation/test map
splits remain256/32/100. A preflight batch accepted332 training scenarios across
190 maps,322 validation scenarios across32 maps, and348 test scenarios across
99 maps. An oracle followed actual simulator transitions for all1,002 cases:
all exited without waking the sleeper, taking damage, or killing. These oracle
paths are used only to check feasibility, never supplied as training labels.
Evaluation practice banks cover all nine player profiles and use eight combat
futures per scenario. Starting source and both continuations get greedy and
sampled evaluation. Ordinary test panels cover seen stats, held-out enemy stats,
and ordinary-stat retention. Test uses the fixed1M endpoint, with no selection
using test outcomes. One training seed is an initial screen, not a replication.

Preflight also checks hidden stairs, exactly one visible sleeping enemy,
safe-frontier reachability, mixed autoresets, and unchanged step reward
accounting. The existing production simulator supplies all transitions.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-sleeper-bypass/preflight.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-sleeper-bypass/inspect_stalls.py
gpu-d1/.venv/bin/python -u gpu-d1/diagnostics/d1-sleeper-bypass/run.py
```

Artifacts use the existing4GiB storage budget /10GiB free-space floor. Only two
checkpoints plus latest resume state per arm are retained. Native builds, raw
banks, checkpoints and logs are ignored; compact diagnostics and reports are
tracked. Generated samples retain no information from held-out maps in training.

## Completed pilot and runner-up actions

Both arms completed1,000,448 additional decisions. Control training took52.3s
and1,162,912 physical turns; practice took55.5s and1,186,543 turns. The whole
pipeline, including evaluation, took557.6s. Practice completed1,543 curriculum
episodes and3,786 ordinary episodes; control completed4,729 ordinary episodes.

Held-out ordinary-floor exits:

| Panel / policy mode | Starting5M | Control +1M | Practice +1M |
| --- | ---: | ---: | ---: |
| test_seen_sampled | 24.28% | 23.28% | 24.67% |
| test_seen_greedy | 14.67% | 12.44% | 13.00% |
| test_unseen_enemies_sampled | 28.89% | 26.44% | 27.11% |
| test_unseen_enemies_greedy | 19.11% | 16.11% | 16.61% |
| ordinary_sampled | 99.50% | 99.25% | 99.12% |
| ordinary_greedy | 96.13% | 94.50% | 93.88% |

Practice has small advantages over control on the dangerous panels, but all
paired map-bootstrap95% intervals include zero. There is no convincing ordinary
floor improvement from this one-seed1M pilot, and greedy performance remains
below the starting checkpoint. These intervals exclude training-seed variation.

In the original27 WAIT stalls, the second-highest joint action is MOVE in all27.
Its preferred direction avoids waking the visible sleeper in24/27, matches the
safe-frontier first step in16/27, and follows the original frontier in only2/27.
Mean action-type probabilities are77.95% WAIT and22.05% MOVE. Mean probability of
the single best directional move is15.44%; conditional on MOVE, its mean share
is75.90%. Thus a useful directional alternative often already exists below the
MOVE-versus-WAIT choice. A safe first step is not proof of a successful detour;
the earlier repeated no-idle-WAIT intervention still timed out in79.63% of futures.

Compact final results: `results/d1-sleeper-bypass-training.json`. Regenerate with
`gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-sleeper-bypass/summarize.py`.

### Does the damage-cap1 intervention encourage approach or bypass?

On the same27 captured states, changing only the visible enemy damage cap to1
makes greedy choose MOVE in17 and WAIT in10. Of those17 moves,13 reduce
Chebyshev distance to the sleeper and wake it; four increase distance. Ten
follow the original frontier, and one follows the safe alternative frontier.
Across all27 states, the preferred conditional MOVE direction changes in16.

The probability mass breakdown is particularly clear:

| Immediate action category | Original damage | Damage cap1 observation |
| --- | ---: | ---: |
| WAIT |77.95%|37.36%|
| MOVE that wakes sleeper |4.45%|43.83%|
| MOVE that does not wake sleeper |17.60%|18.81%|

Thus almost all additional movement probability goes to approaching/waking the
now-apparently-weak enemy. It is not mainly increased commitment to the previous
bypass direction. These are first-action counterfactuals: actual simulator damage
was not changed and no complete detour or fight outcome is established here.
