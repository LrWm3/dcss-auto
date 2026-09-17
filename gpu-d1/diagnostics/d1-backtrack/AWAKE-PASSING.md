# Awake enemy and room to pass it

Completed 2026-09-17, frozen policies only. This extends the known-stairs-beyond-
enemy test in two steps: first start the strong enemy awake in the original
one-tile corridor, then widen the section around it for both sleeping and awake
starts. All four enemy-to-stair distances (4/8/16/24), eight symmetries, three
checkpoints, both policy modes, and 32 futures per cell are retained. Each full
screen contains 18,432 episodes, including unchanged no-enemy/weak controls.

## Controlled changes

Awake setup changes only the strong enemy's awake flag. Starting energy stays
70. A paired preflight verifies that the entire initial observation differs
only at its sleep-status field, with identical legal-action masks. Physical
motion changes after the episode begins, as intended. Weak enemies still start
asleep in every screen.

The passing variant adds a 7x5 room, x=4..10 and y=-2..2, around the enemy at
(7,0). Player starts at (0,0); stairs remain beyond the room at x=7+D. The return
corridor to x=-8 remains one tile wide. The remembered walk through the room
precedes insertion of the enemy, just as in the previous synthetic setup.
Both initial navigation guides still point toward the enemy. Added space
permits passing a living, awake enemy; it does not guarantee a safe crossing.
The room also changes local geometry and monster movement, not just legality.

## Model results

Percentages below aggregate 1,024 strong-enemy trials per model/mode across all
four distances and eight orientations. Raw reports retain the individual cells.

| Setup and action selection | Starting5M | Ordinary6M | Practice6M |
| --- | ---: | ---: | ---: |
| Narrow, sleeping, greedy (previous) | 0% | 0% | 0% |
| Narrow, sleeping, sampled (previous) | 14.55% | 15.33% | 15.23% |
| Narrow, awake, greedy | 21.88% | 15.63% | 11.72% |
| Narrow, awake, sampled | 15.82% | 15.82% | 14.45% |
| Passing room, sleeping, greedy | 0% | 0% | 0% |
| Passing room, sleeping, sampled | 23.34% | 19.34% | 19.53% |
| Passing room, awake, greedy | 19.14% | 28.13% | 19.53% |
| Passing room, awake, sampled | 18.07% | 22.07% | 20.41% |

**Every successful strong-enemy model episode killed the enemy. There were zero
exits with it alive in any of these screens.** No-enemy and weak-enemy controls
all exited; policies also killed the weak enemies rather than passing them.

Sleeping-room greedy behavior remains the same one-step visibility loop:
maximum backward displacement exactly one tile, no WAIT actions, no wakeups,
100% timeouts. Sampled sleeping-room failures are mostly deaths; ordinary and
practice checkpoints also have 19 and 154 timeouts respectively out of 1,024.
Starting-checkpoint sampled has no timeouts.

Awake starts eliminate all timeouts in both geometries: every episode ends in
exit or death. The enemy approaches instead of staying behind the visibility
boundary. Representative room traces show waiting and retreat, followed by
combat, rather than committing to the detour. The room's additional space does
not translate into successful live-enemy bypasses. These aggregate rates do
not establish statistically reliable checkpoint differences or generalization.

## Verified passing route

A separate fixed route, with no attacks, provides a feasibility witness:

```text
(0,0) -> (1,0) -> (2,0) -> (3,0) -> (4,-1) -> (5,-2)
      -> (6,-2) -> (7,-2) -> (8,-2) -> (9,-1) -> (10,0)
      -> continue straight to the first stair -> descend
```

Rotate/reflect the whole route with each map. Under actual simulator transitions,
this route exits in **704/1,024 strong-enemy trials (68.75%)**, for both sleeping
and awake starts. Every such exit leaves the enemy **awake and alive**. Remaining
320 trials die; none remains unfinished. Sleeping/awake results match because
the route approaches immediately and wakes the sleeper on its first move;
the two variants then share the same initial energy progression. Thus this is
not proof that passage can be made completely safe.

The route uses predefined geometry, is not a learned policy or an optimal
controller, and is not installed in the model evaluations. It is evaluated for
40 steps, enough for an unobstructed route to the farthest stair. It is open-loop:
weak-enemy checks have 712 exits and 312 unfinished cases when interference
blocks the fixed action sequence; these are explicitly reported as unfinished,
not deadline timeouts or successes. Empty-map checks all exit. This limitation
does not affect the strong-enemy witness, where every case terminates.

Combat seeds repeat across orientations/distances, so 1,024 is an episode count,
not a claim of 1,024 independent scenarios. The witness nevertheless establishes
that successful nonlethal passage is possible in this exact simulator, while
none occurred in the evaluated policies. The result supports testing instruction
or training for committing to a bypass; it does not yet identify whether the
main obstacle is navigation representation, missing experience, or the objective.

## Reproduce and artifacts

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-backtrack/beyond.py --awake
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-backtrack/beyond.py --passable
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-backtrack/beyond.py --passable --awake
```

Use matching flags with `beyond_trace.py`; run `beyond_route.py` and
`beyond_route.py --awake` for the passing witnesses. Runtime including native
build and maps: 39.98s narrow awake, 94.21s room sleeping, 42.15s room awake.
Trace/witness checks are additional short evaluations.

Tracked JSON reports (including representative traces and, for room variants,
fixed-route outcomes):

- `results/d1-stairs-beyond-enemy-awake.json`
- `results/d1-stairs-beyond-enemy-passable.json`
- `results/d1-stairs-beyond-enemy-awake-passable.json`

Generated artifacts use matching isolated `learning-runs/` directories and
remain ignored. Default sleeping/narrow behavior is preserved.
