# Known stairs beyond a dangerous sleeping enemy

Completed 2026-09-17. Frozen evaluation, no training. Three checkpoints × two
policy modes × four stair distances × eight rotations/reflections × three enemy
conditions × 32 random futures = 18,432 episodes. Runtime including maps and
native compilation: 78.35 seconds.

## Setup

```text
closed end -------- @ ------ sleeping enemy -------- known stairs
                   x=0           x=7                x=7+D
                                                     |
                                              unseen continuation
```

D is 4, 8, 16, or 24 tiles **from the enemy to the first stair**, not from the
player. The other two working stairs are one/two tiles perpendicular to that
endpoint. The corridor is one tile wide, so the enemy blocks the only route.
There is no safe alternate route to the stairs. The rear closed end is x=-8.

Player full HP18/damage cap4; enemy absent, weak HP6/cap4, or strong HP24/cap20.
Speed and all other simulator settings match the previous tests. The sleeper
starts visible, outside its six-tile wake radius. All three stairs are known.
The nearest frontier is in the unexplored continuation beyond the stairs. Both
the observed frontier and stair guide initially point toward the enemy; native
and Python assertions check this across every geometry/condition.

History walks from x=-8 to the first stair and back to x=0 **before inserting
the sleeping enemy**. This is a deliberate synthetic encounter intervention,
not evidence that the player could previously cross this enemy without waking
it. Terrain and stair knowledge come from ordinary observation updates along
that walk. Its 8+2*(7+D) physical turns count toward the same 2048-turn deadline.
The starting player has full health, and all actions after setup are free.

## Results

Every no-enemy and weak-enemy case exits, for all checkpoints, modes, distances,
and orientations. Weak enemies are killed before exiting.

For the **strong enemy, greedy evaluation has 0 exits, 0 deaths, and 100%
timeouts**, for every checkpoint/distance/orientation. There are no enemy wakeups
and no WAIT actions. Maximum backward displacement is exactly one tile.
Representative first-32-step traces for every checkpoint and distance show:

1. Enemy visible at x=0: move west to x=-1.
2. Enemy no longer visible: move east to x=0.
3. Repeat.

The known stair destination therefore does not break the movement loop when
its route points through the threat.

Sampled strong-enemy exit percentages (256 episodes per cell):

| Tiles beyond enemy | Starting5M | Ordinary continuation6M | Bypass practice6M |
| --- | ---: | ---: | ---: |
| 4 | 18.75% | 15.63% | 14.06% |
| 8 | 15.23% | 14.84% | 16.41% |
| 16 | 12.89% | 14.45% | 10.94% |
| 24 | 11.33% | 16.41% | 19.53% |
| All distances | 14.55% | 15.33% | 15.23% |

All sampled strong-enemy trials wake the enemy; all successful exits kill it.
Every non-exit is a death, with **no sampled timeouts**. Average post-start turns
until either exit or death are 35.65 / 145.50 / 178.80 for source/control/practice.
These are not average successful-exit times. The latter checkpoints delay
engagement longer without a clear improvement in eventual survival.

## Interpretation and limits

Together with the previous test, this shows a conditional behavior: a known
stair guide works very reliably when it points away from the threat, but a
known destination through the threat does not cause greedy policies to commit
to crossing. The local visibility boundary still changes their movement
preference. This is not just confusion between exploration and stair goals.

There is no consistent distance trend shared by the checkpoints. The source's
sampled rate declines with distance but the other two do not reproduce it;
256 combat futures per cell and these related checkpoints do not establish a
learned valuation of exit distance. History length, seen terrain, and the
initial time fraction also vary with corridor length.

This geometry deliberately supplies no safe bypass. We have not established
that deaths are avoidable, that fighting is optimal under the exact reward,
or that a better controller could exit reliably. The main evidence concerns
policy behavior, not a missing guaranteed solution. Sampled success reflects
surviving combat, rather than sneaking past the sleeper. Greedy repetitions
without combat are repeated deterministic behavior, not independent evidence.

## Reproduce

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-backtrack/beyond.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-backtrack/beyond_trace.py
```

Tracked results and representative traces: `results/d1-stairs-beyond-enemy.json`.
Generated artifacts: ignored `learning-runs/d1-stairs-beyond-enemy/`.
The original backtracking map generator retains its default behavior.
