# 15x15 vision with and without frontier travel

2026-09-15. Isolated branch: `branches/vision15-frontier-v1`.
Two fresh seed-0 runs to 30M policy decisions: `vision15_no_travel` and
`vision15_travel`. Both use 24 required ordinary enemies, **zero ogres**, a
512-physical-turn deadline, 256 training layouts and the existing 32 validation
layouts × 32 episodes. The no-travel arm still receives the existing frontier
pointer and route hint; the intervention is availability of the travel action.

## Vision and observation changes

Player vision grows from a 9×9 window (radius four) to **15×15 (radius seven)**,
still gated by each map's native cached wall-blocked LOS. No cache recomputation
is necessary: existing per-origin 17×17 masks already cover the larger window.

Terrain discovery, floor exploration rewards, visible-enemy HP grids and records,
encounter counters, visibility channels, and travel masking/interruption all use
the new radius. Monster waking deliberately retains its six-tile radius plus
monster-origin LOS; already-awake pursuit is unchanged. Thus a player can now
see some sleeping enemies before entering their wake radius.

The remembered perimeter moves from radius five to radius eight so it stays just
outside the current view, growing from 40 to 64 cells. It exposes remembered
terrain only, not hidden geometry. This and the larger spatial channels expand
the observation to 958 values. The network remains two 128-unit hidden layers;
its input layer expands accordingly. Action counts are nine without travel and
ten with it. Compile-time `FRONTIER_TRAVEL` changes only action availability and
execution; both arms share observation and diagnostic layouts.

| Observation | Offsets (zero based) |
|---|---|
| Remembered local terrain, 15×15 | 0–224 |
| Visible local enemy HP, 15×15 | 225–449 |
| 40 discovery-ordered enemy records × 5 | 450–649 |
| Player HP, elapsed-turn fraction, absolute x/y | 650–653 |
| Remembered radius-eight ring | 654–717 |
| Nearest-frontier pointer | 718–724 |
| Eight-way route hint | 725–732 |
| Current 15×15 visibility | 733–957 |

Rewards, PPO hyperparameters, optional-label setting, enemy stats and training
seed match the zero-ogre 9×9 comparison. The travel action keeps its established
semantics: select a fixed reachable frontier through known floor, execute normal
game turns, stop on arrival or enemy sighting or episode end. One trip counts as
one PPO decision with summed rewards and no duration-adjusted discount. Both
arms record physical turns as well as policy decisions and training time.

## Queue and storage

Queued at 20:32 ADT, after successful completion of all four runs in
`results/vision-budget-comparison-queue.json`. The waiter shares the predecessor's
queue lock and verifies every final result before launch; it refuses to proceed
if that queue stops unfinished. Expected new-pair runtime roughly 10–14 minutes,
subject to measured full-batch throughput. Retention: one latest/resumable and
one best checkpoint per arm, 2 GiB suite cap, 5 GiB free-space reserve.

Suite: `learning-runs/vision15-frontier-30m`.
Log: `results/vision15-frontier-30m-console.log`.
Launch metadata and exact plan are alongside the log.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-frontier-v1/scripts/queue_after_budget.py \
  --after-queue gpu-d1/results/vision-budget-comparison-queue.json \
  --output gpu-d1/learning-runs/vision15-frontier-30m --steps 30000000 --seeds 0
```

## Validation

Both end-to-end smoke runs passed. `results/vision15-frontier-validation.txt`
records 8,400 CPU/CUDA policy transitions per arm; the travel arm covered 11,000
physical turns and 969 travel uses. Checks include native occlusion/knowledge
leaks, macro interruption and timeout replay, observation clock, reward sums,
ogre-free diagnostic invariants, and inactive environments remaining frozen.

An independent decoder compared the spatial visibility channel against cached
LOS bits, including 22,928 visible cells beyond the old radius four. It also
reconstructed remembered terrain and checked every radius-eight perimeter cell.
Both action sets produced identical observations and dynamics when given the
same primitive actions. Native reveal scratch capacity grows to 225 cells and
all active observation offsets use the expanded schema.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-frontier-v1/scripts/test_vision15.py \
  gpu-d1/learning-runs/vision15-frontier-smoke
```

Interpretation: this is a single-seed screen. Comparing the two new arms tests
travel with larger vision. Comparing against 9×9 additionally changes observable
area, memory-ring extent, input-layer size, and opportunities for discovery
rewards; it is not a compute-matched or reward-normalized comparison.
