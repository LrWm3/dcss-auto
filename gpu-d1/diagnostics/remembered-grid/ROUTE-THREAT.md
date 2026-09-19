# Destination routing with remembered variable-strength enemies

This is a first seed-0 imitation/DAgger screen, not PPO. Both arms start from the
selected enemy-free destination policy and run 2000 updates. The new input
weights start at zero; common navigation weights are copied. Tactical primitive
logits are newly introduced, so this is not a behavior-preserving expansion of
that checkpoint. The earlier variable-strength tactical policy is not reused.

## Inputs and actions

The policy receives the exact remembered 80×70 terrain, visited cells, discovered
stairs, player location, previously selected destination and elapsed-time
fraction. Added enemy channels contain last-observed HP, maximum HP, damage cap,
awake state, age (capped at 255 physical turns), presence, currently visible, and
stale. Player HP fraction, maximum HP and damage cap are supplied separately.
There are no monster identities, speed features, frontier arrows or route fields
in the network input. All enemies retain the existing common speed 10.

Memory stores every previously seen enemy, up to the environment's 40-slot
capacity; the experiment has 24 active enemies. Hidden movement, damage,
awakening and death do not update records. A visible empty square invalidates a
record there; recognizing a currently visible enemy updates its old record
rather than duplicating it. Internal slot identity is used only for this visible
association and is not an observation. A remembered position is an uncertain
last-seen location, not a known current occupant. Episode reset clears memory.

Actions select a reachable frontier-region/stair destination, continue the last
route, or take any of the 19 original primitive actions (move, attack, wait,
rest, exit). Destinations/continuation are unavailable with an awake enemy in
vision, but are available with visible sleepers. Individual moves remain legal
for retreat in either case. BFS executes one step through remembered floor;
it does not avoid threats. Rest keeps its production interruption behavior and
charges physical turns. The deadline is 2048 physical turns.

## Matched comparison

- `visible`: zero all enemy channels for enemies outside current vision.
- `memory`: preserve last-seen records outside vision.

Both have the same architecture, initialization, legal actions, destination
memory, teacher targets, seeds, update count and native layout split: 64 training,
16 validation, 32 test layouts. Both use the calibrated anonymous distribution:
player maximum HP 10/18/30, damage cap 2/4/6; six enemy templates from the existing
calibration, independently sampled for 24 enemies. One third of resets use
clumped placement. Evaluation retains the same stat catalogue on held-out maps;
it is not a test of unseen stat combinations.

Training uses ordinary floors only, two FIFO buffers of 2048 states each,
equal expert/learner losses, batch 32 per buffer, Adam 1e-4 and 2000 updates.
Learner data refresh every 100 updates and expert data every 500, with 256-step
collection windows. Validation every 500 selects on exits over 32 fixed episodes.
Only latest/selected checkpoints are retained. Reports separate training and
collection time from evaluation. Three serial jobs: teacher reference, visible
learner, remembered learner. Failures stop the queue.

## Teacher and interpretation

The teacher sees the same remembered observations, not simulator truth. It uses
the existing measured full-health duel risks with a 15% avoidance threshold.
Below full health it adds a conservative injury heuristic, not a newly calibrated
risk estimate. It avoids a six-tile region around remembered dangerous enemies,
rests when legal, attacks weak adjacent enemies, waits for weak awake enemies,
and attempts to increase separation from dangerous awake enemies. If cornered,
it attacks. This is a scaffold, not an optimal survival oracle.

For navigation labels it searches safe known floor. If the terrain-only
executor's first step disagrees with that safe route, the teacher labels a
primitive move instead; execution never silently gains threat-aware routing.
Both learners receive the same memory-informed labels. Consequently the
visible-only learner may face ambiguous targets: that is part of the information
ablation, not evidence of an optimizer defect. Persistent chosen destinations
may themselves help it compensate for absent enemy memory.

Test panels report ordinary-floor exits/deaths/timeouts and the original rotated
L-corridor pressure cases: 4/8/16/24 backtracking tiles, eight orientations,
weak/strong sleepers, stairs unknown versus already known. Pressure geometries
are excluded from training and selection. Metrics include turns, kills, waits,
reversals and decisions containing stale threats. The remembered learner also
gets an evaluation-only memory erasure intervention. Other stairs-beyond-enemy
and awake-passing families remain follow-ups, not covered by this initial screen.

A gain would support the usefulness of remembered threats with executable
alternative destinations. It would not demonstrate that PPO discovered avoidance,
that the teacher is optimal, or that stale positions are accurate. Failure could
come from teacher quality, insufficient training, tactical control, or candidate
selection. Compare the teacher before interpreting learner failures.

## Reproduction

```
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_route_threat.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/route_threat_suite.py
```

The check exercises real LOS transitions, observation-only memory updates,
multiple records, reset, sleeping/awake action availability, variable player
normalization, identical ablation labels/masks and gradients in new input channels.

## Completed results (2026-09-18)

The suite finished in 22m06s. Both learned arms completed 2000 updates, with
training/collection times of 179.5s (visible) and 181.6s (memory), excluding
validation/test evaluation. Validation selected update 2000 for visible and 1000
for memory; these are not equal-update selected checkpoints. Each ordinary test
has 128 episodes. Each pressure category has 32 cases: four distances and eight
orientations. Evaluations are greedy, with one training seed.

| Policy | Ordinary exit | Ordinary death | Weak/unknown stairs exit | Weak/known stairs exit | Strong/unknown stairs exit | Strong/known stairs exit |
|---|---:|---:|---:|---:|---:|---:|
| Observation-limited teacher | 28.91% | 66.41% | 100% | 100% | 100% | 100% |
| Visible-only learner | 11.72% | 74.22% | 100% | 100% | 81.25% | 100% |
| Memory learner | 11.72% | 78.91% | 65.63% | 93.75% | 43.75% | 65.63% |
| Memory learner, stale channels erased at evaluation | not tested | not tested | 68.75% | 93.75% | 46.88% | 65.63% |

Strong/unknown successes at backtracking distances 4/8/16/24 were 7/6/6/7 of eight
for visible-only, and 4/4/3/3 for memory. Visible-only escaped with the strong
enemy alive in 24/32 cases; memory did so in 12/32. Visible-only's six failures
were deaths, not timeouts. Memory had sixteen deaths and two timeouts.

Both initial expanded policies had zero exits on the 32-case validation panel.
The visible learner's final selected validation exit rate was 12.5%; memory's
selected rate was 21.875%, falling to 9.375% at update 2000. That validation
advantage did not transfer to the held-out ordinary test (both 15/128 exits).
The memory learner also showed extensive waiting/reversals on pressure cases.

Interpretation: destination routing plus training can solve many of the old
backtracking failures without stale enemy channels. A persistent selected-goal
marker is itself memory; visible-only is not a memoryless policy. This is not an
isolated causal comparison against the older frontier-arrow policy, because the
action interface, architecture, initialization and training all changed.

Explicit enemy memory showed no benefit in this seed and budget. Erasing stale
channels after training recovered only one strong/unknown case, so immediate
interference from stale inputs alone does not explain the gap. Training dynamics,
checkpoint selection, and learned tactical behavior remain possible causes; none
is established by this screen. These results do not show that remembered threats
are unnecessary in general or inherently harmful.

The teacher solves every pressure case but only 37/128 ordinary floors, with 85
ordinary deaths. Ordinary-floor teacher behavior is therefore a major limitation
of the training setup, though its success rate is not a theoretical ceiling for
a learner. Neither learner is a successful general variable-strength navigator.
