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

## PPO continuation

`route_threat_ppo_suite.py` runs visible-only and memory sequentially from their
respective validation-selected imitation checkpoints, seed 0, to 500,000 sampled
policy decisions each (rounded up to the next 2048-decision rollout). The starting
checkpoints are different and were selected at different imitation updates; this
is a within-arm before/after PPO screen, not an isolated equal-initialization
memory ablation. Evaluation occurs before training and at 100k/500k decisions:
128 ordinary held-out episodes in greedy and sampled modes, plus greedy pressure
cases. No checkpoint is selected using these test scores.

Reward is +1 for exiting and -0.00001 per physical turn, with zero additional
death, kill or reveal rewards. Gamma is 1, GAE lambda .95. REST accumulates its
actual physical-turn cost; routing consumes one physical turn per step. PPO uses
32 environments, 64-decision rollouts, minibatches of 64, four epochs, clip .2,
actor LR 1e-5, value LR 1e-4, zero entropy bonus, and gradient norm .5. Stop the
remaining updates in a rollout if pre-update minibatch approximate KL exceeds
.01. This is an early-stop heuristic, not a guaranteed trust-region bound.

The critic is a new 16→64→1 head with zero initial output. It consumes detached
actor features, so value loss cannot directly damage the policy encoder. Actor
updates can still change those features and the policy; this does not guarantee
preservation of imitation performance. There is no imitation loss, teacher
label computation during PPO collection, or frozen-policy anchor.

Each finished episode resets independently, clearing its selected destination
and enemy memory, while continuing episodes remain unchanged. Rollout cutoffs
bootstrap from the next value; actual exits/deaths/deadline terminations do not.
Replay stores exact FP16 observations (including selected destination), masks,
actions and behavior log probabilities. A pre-update audit bounds log-probability
replay error at .01; small AMP differences can arise from batch-32 collection
versus batch-64 replay. Tests cover reset isolation, value-gradient isolation,
terminal/cutoff GAE boundaries, physical-turn costs, and actual PPO updates.
Evaluation preserves the training random-number streams. Reports include training
time, decisions/s, physical turns, outcomes, KL stops and AMP skips. Checkpoints
are limited to 100k, 500k and latest; no trajectory archive is retained.

## Performance pass

PyTorch CPU/CUDA profiling identified observation export as the dominant rollout
GPU cost (76% in an eight-step trace). The serial export took about 8 ms for 32
worlds and was unnecessarily called twice per PPO step. The optimized path:

- uses one CUDA block per world to export terrain in parallel;
- exports once after transition and any independent episode resets;
- runs exact observed-grid routing on CUDA, avoiding CPU round trips;
- captures inference in CUDA graphs, with fresh parameter casts every replay;
- uses channels-last convolution weights and skips unused teacher labels in
  learned-policy evaluation.

The architecture still uses 20 spatial updates. Environment batch size, rollout
length, rewards and PPO hyperparameters remain unchanged. Adam/backward remain
eager: an attempted backward capture failed with a CUDA stream-dependency error
and was not retained. Small AMP numerical differences from memory layout are
possible; this is not a claim of bit-identical training trajectories.

Checks found exact agreement with the reference observation exporter on 30
32-world snapshots, and exact GPU/CPU route outputs on 960 state comparisons.
Captured inference reacts to parameter updates and returns independent output
buffers. Maximum channels-last logit difference in the check was 0.00293.

| Measurement | Reference | Optimized |
|---|---:|---:|
| Observation export, 32 worlds | 8.15 ms | 0.032 ms |
| Actor/value inference, 32 worlds | 5.69 ms | 2.97 ms |
| Router, initial CPU timing / GPU timing | 0.92 ms | 0.60 ms |
| Matched 2048-decision PPO smoke | 4.01 s | 2.76 s |

The matched PPO smoke had the same 78 optimizer updates, 30 completed episodes,
4 exits, 26 deaths, 17 rests and 2665 physical turns. A separate warmed timing
with 55 updates achieved 990 decisions/s; it should not be compared as if update
counts were identical. Initial capture costs are included in the smoke but not
steady-state inference timings. End-to-end speed varies with KL early stopping.

The running visible arm is resumed from its 100352-decision checkpoint, retaining
actor, critic, optimizer, scaler and RNG state. That legacy checkpoint did not
contain environment snapshots, so its 32 ongoing episodes restart. A small
unsaved tail is archived in the report rather than counted as retained progress.
New checkpoints include environment and selected-goal state for exact future
continuation. The queued memory arm starts with the optimized implementation.

Reproduce component checks with `check_route_threat_fast.py`; raw profiler traces
stay in the ignored run directory. Tracked `route-threat-performance.json` and
`route-threat-ppo-visible-smoke-optimized.json` contain the measurements.

### PPO update optimization follow-up

`route_threat_ppo.py` now accepts `--compile-updates --hoist-inputs`.
These are opt-in so prior experiment commands retain their implementation.
Compilation applies to replay/update forward and backward; collection retains
its existing eager CUDA graph. Checkpoint parameter names are unchanged.
Hoisting splits each recurrent convolution into an input-only projection,
computed once per forward, and a hidden-state projection at each of 20 steps.
The input projection remains attached to autograd, and biases are added once.
No PPO hyperparameters, observation fields, reward, or action masks change.

Measured on the Quadro RTX 5000 Max-Q, with 64-example update minibatches:

| Implementation | Forward + backward | Fixed-rollout update, median |
|---|---:|---:|
| Eager reference | 16.72 ms | 0.400 s |
| Hoisted input projections | 15.87 ms | 0.385 s |
| Compiled reference | 12.65 ms | 0.290 s |
| Compiled + hoisted | 11.11 ms | 0.238 s |

All fixed-rollout cases perform nine optimizer updates before the same KL
stopping rule fires. The update timing includes the full replay audit.
The combined implementation takes approximately 40% less update time, not
40% less total training time. Cold first forward/backward compilation was
approximately 18–20 seconds; subsequent process starts with compiler caches
were 3–5 seconds. Other shapes/grad modes can require additional compilation.

Four end-to-end rollouts with hoisting alone versus hoisting plus compilation
had identical update counts (50, 101, 48, 34), episode counts, exits/deaths,
rest counts and physical-turn totals. They took 7.54 versus 5.64 seconds:
1087 versus 1453 decisions/s, a 34% throughput gain. The non-hoisted variants
subsequently diverged in KL stopping/trajectories, so their aggregate throughput
is not a controlled speed comparison. These short tests do not establish
long-run learning equivalence or sustained throughput at later checkpoints.

Checks include FP32 forward and per-parameter gradient equivalence of hoisting;
AMP output and aggregate gradient comparisons for every variant; full rollout
log-probability replay checks; and actual optimizer updates. Maximum AMP logit
difference was 0.00449, and gradient relative L2 differences were below 0.82%.
No AMP updates were skipped. Floating-point changes can change later sampled
trajectories and KL stopping; this is not a bitwise reproducibility guarantee.

Reproduce with `benchmark_route_threat_updates.py`; measurements are in
`results/route-threat-update-performance.json`. Compilation requires Python
3.12 development headers, absent from the original machine. For this workspace,
the distro headers were extracted without system installation into the ignored
`learning-runs/remembered-grid/route-threat/compiler-headers/include` directory.
Set `C_INCLUDE_PATH` to that absolute directory and its `python3.12` subdirectory
when launching the benchmark or training with `--compile-updates`; an ordinary
Python development-header installation also suffices. Compilation failures are
reported, not silently replaced with eager execution.
