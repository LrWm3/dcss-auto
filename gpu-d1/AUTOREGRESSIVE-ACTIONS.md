# Conditional directional action policy

Queued after the semantic action experiment: 10M decisions, seed 0. This tests
learned MOVE / ATTACK / WAIT / REST selection with learned direction parameters.
It replaces supplied exploration/approach/weakest-target execution with directional
choices; comparison against the semantic run therefore changes the amount of
supplied behavior, not just architecture.

The same 999 observations, exact D4 averaging, two-layer 128-wide encoder, 24
enemies, 256 training layouts, one-third clumped placement mixture, rewards,
15×15 LOS, sleep status, 2048 physical-turn budget, and validation panel are used.
REST has the same duration-aware rewards/discounting and interruption as the
semantic run. MOVE, ATTACK and WAIT each take one physical turn.

## Policy

Shared encoder feeds a four-way action-type head and the value head. MOVE and
ATTACK use learned 16-dimensional type embeddings concatenated with the encoder
state, then one shared 64-wide tanh direction head producing eight logits.
Both conditionals are computed together for batching, but execution samples type
first and then that type's direction. WAIT and REST have no direction factor in
their likelihood or entropy. PPO uses the sum of type and conditional-direction
log probabilities; entropy is H(type) + expected H(direction | type).

The implementation encodes joint actions as MOVE 0–7, ATTACK 8–15, WAIT 16,
REST 17. This encoding does not mean there is an independent flat 18-way head.
Greedy evaluation selects the most probable type, then its most probable direction
(not the largest joint probability across all 18 encoded actions).

Known walls and visible enemy-occupied tiles mask MOVE directions. Unknown tiles
remain probeable; hidden terrain/enemies do not supply masking information.
ATTACK directions require visible adjacent enemies. Any type with no valid
direction is masked. WAIT always exists; REST requires damaged HP, regeneration,
and no visible awake enemy. Unavailable conditional distributions have dummy
finite logits but zero joint probability, preventing all-masked numerical errors.

D4 averaging leaves type logits invariant and rotates both sets of direction
logits back to world coordinates before averaging. The shared direction head
receives the type embedding separately in every transformed view.

## Interpretation

This policy can learn retreat and target selection, unlike the five-action
semantic controller. It also must learn navigation rather than receive an
exploration macro. A matched flat directional policy would be needed to isolate
factorization itself. Hierarchical type sampling changes initial exploration:
probability is allocated across types before directions, not uniformly across
all legal directional commands. Parameter count and training time are recorded.

## Execution and verification

Scripts are in `branches/autoregressive-actions-v1/scripts`:
`assets.py`, `preflight.py`, `queue_after_semantic.py`, and `run_experiment.py`.
Use `gpu-d1/.venv/bin/python` from the repository root with the full script path.

Tests cover native action masks, attack/movement equivalence to primitive turns,
REST interruption and exact deadlines, unknown-wall masking, D4 equivariance,
joint probabilities/entropy/gradients with unavailable types, small PPO training,
and checkpoint resume.

The queue waits on the semantic runner's lock and requires its completed result;
if that run exits unsuccessfully, the queue marks itself blocked. The queued plan
hashes sources and refuses source drift before launch. Artifacts stay under
ignored `learning-runs/autoregressive-actions` with a 2 GiB budget and 10 GiB
minimum free space. Validation checkpoints are approximately 0, 1M, 3M, 5M, 10M;
final summary is `results/autoregressive-actions-training.json`. Action counts
are reported by type, alongside physical turns and training time.
