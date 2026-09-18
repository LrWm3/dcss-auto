# Learned spatial processing versus analytical route execution

Three fresh, seed-0 learned policies use the same exact remembered 80×70 maps,
native layout splits (64 train/16 validation/32 test), 1024 physical-turn deadline,
and 2000 gradient updates. This is a supervised/DAgger screening experiment, not
PPO and not a continuation of the old coarse-model checkpoint.

| Arm | Decision | Map computation |
|---|---|---|
| One-pass | Individual movement/wait/exit action | One spatial gated update |
| Recurrent spatial | Individual movement/wait/exit action | Twenty spatial gated updates per decision |
| Analytical routing | Destination, CONTINUE_ROUTE, wait, or exit | Twenty spatial updates, then BFS executes one step |

These models have identical parameter shapes/initialization. They contain both
heads, but only the relevant head receives training. Unlike a temporal GRU, the
spatial recurrence runs afresh within each decision. A lossless 4×4 space-to-depth
input feeds a 16-channel recurrent grid at 18×20 resolution; the decoder combines
upsampled features with the exact full-resolution input. No supplied distance,
recommended direction, or shortest-path field enters either network.

The one-pass arm has a deliberately short spatial receptive field and is a
reactive control, not an equivalent replacement for the previous coarse/global
policy. The 20-update arms can exchange information over the full map width.
This gives a mechanism for spatial computation but does not guarantee that it
learns planning or preserves fine connectivity through the learned features.

## Analytical interface and information boundary

`route_candidates.cpp` receives only exported remembered-grid observations and
legal-action masks. It has no access to simulator state, hidden terrain, map
tables, fixture distances, or scenario identifiers. BFS traverses known floor,
using the simulator's eight movement directions and unrestricted diagonal rule.

Candidates are reachable discovered stairs plus one fixed-coordinate
representative per connected frontier region. A frontier is known floor next to
unknown terrain. Representatives are chosen by coordinate order, not distance.
The policy receives a candidate mask and its previous selected-goal marker;
these are extra scaffolding relative to direct-action policies and are part of
the treatment. BFS returns a first move only to the executor, never to the model.
Every destination or CONTINUE_ROUTE decision executes **one** physical step.
The policy can replace a destination at any decision. Arrival or an unreachable
goal disables continuation. There are no enemies in this initial comparison.

The training controller prefers nearest reachable known stairs, otherwise the
nearest candidate frontier. It labels direct actions for the movement policies
and destinations/continuation for the route policy. Both use the same remembered
information, but their targets/action spaces differ. This is a comparison of
complete approaches, not a pure equal-information architecture ablation.

## Controls and tests

The deterministic controller reached stairs in 100% of the initial validation
cases (middle and longer routes; both known-stair and exploration categories).
The suite evaluates it on held-out test cases too. A random-destination baseline
chooses uniformly among candidates, commits until arrival, and exits when able;
this separates learned selection from the benefit of routing/commitment alone.

Hand-constructed checks cover a straight corridor, forced U-shaped detour,
disconnected remembered floor, unknown terrain that cannot be crossed, candidate
validity, continuation, reset, and gradients through spatial recurrence. All
three learning arms passed two-update smoke tests.

Training uses equal expert/learner replay losses, batch 32 per buffer, FIFO
capacity 4096 per buffer, Adam 3e-4, and 256-step collection windows. Validation
occurs every 500 updates and selects the checkpoint; held-out test success,
timeouts, mean turns, and reversals are then reported. Training/collection time
excludes evaluation. Update budgets match; elapsed time and collected-decision
counts need not match, and are recorded separately. Only latest and selected
checkpoints are kept to bound disk usage.

`route_comparison_suite.py` runs all jobs sequentially and produces
`gpu-d1/results/route-comparison-summary.json`. If a job fails, the queue stops
instead of reporting a partial comparison as finished. See individual JSON
reports for per-case results and validation curves.

Interpretation: planner gains over direct actions indicate the usefulness of
delegating route execution, but should also exceed random committed destinations
before being attributed to learned strategic selection. Recurrent gains over
one-pass suggest benefits from wider/repeated spatial processing. Failure on
unknown stairs despite success on known stairs isolates exploration selection
as a remaining problem. No result yet establishes combat competence or retreat.
