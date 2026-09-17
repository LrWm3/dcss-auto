# Remembered-grid navigation, first demonstration

This is an isolated supervised navigation experiment on small procedural floors,
not a new ordinary-D1 policy or a PPO result. It reuses the current simulator's
movement, diagonal corner cutting, wall-blocked 15x15 LOS, sleeping-enemy waking,
combat, regeneration, REST and DESCEND transitions. The new policy chooses every
individual action during evaluation. There are no frontier/stair arrows, route
lengths, distance fields, automatic travel, or teacher overrides in its inputs
or evaluation execution.

## Representation and experiment

The active floor occupies a 32x32 region of the native 80x70 map. The exact
remembered terrain is maintained by the existing observation updates. Separate
channels represent known floor, known wall, actual player visits, current LOS,
remembered stairs, player location, last-observed enemy HP/damage/awake status,
age, and existence. All-zero terrain means unknown. Enemy observations update
only in LOS; a stale marker is cleared when observation contradicts it. This
first fixture suite has at most one monster, so its memory is deliberately a
single-record implementation; it must be expanded before ordinary multi-enemy
use. Player HP and elapsed turns divided by 2048 are additional policy inputs.
The inherited time scaling is retained even though this small task ends at
256 turns; its fixed deadline therefore corresponds to a time input of 0.125.

The navigation policy is trained from scratch with 19 joint action logits
(MOVE directions, ATTACK directions, WAIT, REST, DESCEND). It is not a warm
start of the earlier autoregressive combat policy. All new representation arms
share this same action head.

Two learned spatial encoders are implemented:

- `conv`: a detailed local CNN plus a global strided CNN/flattened summary.
- `spatial`: the same local CNN, plus a U-net that combines fine spatial features
  with coarser context, then reads features around the player's location.

The U-net's convolution, pooling, upsampling, and feature combination are all
neural processing. It performs no BFS or fixed path propagation. Keeping the
underlying map exact does not make the network's intermediate features lossless.

Arms are `local` (15x15 remembered crop only), `terrain` (local/global terrain but
only currently visible monster records), and `memory` (local/global terrain and
last-observed monster record). Global-disabled arms still have local terrain
memory within the crop. No recurrence or intent memory is added.

Training fixtures comprise 128 mazes with narrow passages, small rooms, diagonal
pockets and occasional loops, plus 32 threat junctions. Validation uses 32 + 32,
test 64 + 32, and larger/longer tests 32 + 32. Actual terrain arrays are disjoint
across all four sets. The long mazes use 6x6 construction nodes instead of 4x4 or
5x5. Pressure backtrack lengths are 4/6/8/10 in training, 5/7 in validation, 9/11
in test, and 12/14 in the long panel. These are limited synthetic geometry
families, not the existing Crawl D1 corpus.

Each maze supplies four placements, each in two conditions:

1. Known stairs: a real preceding walk from stairs to the start reveals a return
   route. The history is included in elapsed turns and visited terrain.
2. Exploration: only the initial LOS is known; the stairs must be discovered.
3. Pressure fixtures: a real preceding walk ends seven tiles from a visible
   sleeper (24 HP, damage cap 20). An alternate unexplored branch contains the
   stairs. Player HP/damage are fixed at 18/4. The sleeper's wake range is six
   tiles with native LOS. No threat labels or actual hidden positions are inputs.

All three stairs work, and only explicit DESCEND exits. Evaluation uses a
256-physical-turn deadline including history on validation and the main test.
The longer-route panel uses 512 turns because its setup walk plus return can
exceed 256; this is a length-generalization test with an ample budget, not a
matched-deadline comparison.

## Teaching and reporting

The teacher runs BFS **only to construct training action labels**, traversing
remembered floor and using observed stairs/frontiers. It conservatively avoids
squares within six tiles of a remembered dangerous enemy. It does not inspect
hidden stair locations or unknown terrain when choosing actions. It is not an
optimal tactical controller. A teacher-only rollout first verifies feasibility.

Training is behavior cloning plus corrective labels on student-visited states
(DAgger-style data collection), not PPO. Successful teacher trajectories remain
in a separate 65,536-state ring buffer; a 32,768-state buffer stores mixed
teacher/student rollouts. Loss equally weights samples from the two buffers.
Each update samples 256 supervised examples total. Training augmentation rotates
and reflects grid, player coordinates, action masks and action labels together.
Reset kinds are sampled uniformly; trajectory lengths differ, so state counts
are not balanced by kind. Mixed-rollout teacher probability declines to 0.1.

The frozen checkpoint with highest mean validation exit rate across the three
conditions is selected before test for the spatial arms; the simple CNN uses its final checkpoint. Evaluation includes greedy and sampled
policies. Layout clustering matters: different placements on the same map are
not independent map samples. One training seed does not establish cross-seed
reliability. A separate paired-goal probe keeps local observation and walked path
identical but changes which distant branch contains remembered stairs. First
branch choice is more diagnostic than eventual exit on that probe.

Checkpoint selection uses validation only. Reported training time excludes
validation rollouts; the first CNN/U-net runs additionally included validation
environment-construction overhead, fixed for the subsequent control runs. Training time
includes demonstration collection/corrective labels and optimizer updates,
but excludes fixture creation, compilation and initial environment loading.
Decision counts exclude scripted reset histories and count training rollout
decisions, some selected by the
teacher; supervised-example counts include repeated sampling. These are not
comparable to an equal number of autonomous PPO decisions.

## Execution and checks

```sh
mise exec uv@0.12.3 -- uv pip install --python gpu-d1/.venv/bin/python \
  -r gpu-d1/diagnostics/remembered-grid/requirements.txt
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/preflight.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_default_reset.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/run.py --preflight
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/run.py \
  --architecture spatial --arm memory --updates 12000
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/run.py \
  --architecture spatial --arm local --updates 12000
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/run.py \
  --architecture spatial --arm terrain --updates 12000
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/run.py \
  --architecture spatial --arm memory --evaluate
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/probes.py \
  --folder memory-spatial
```

`--resume --updates N` continues to N optimizer updates, not N additional
updates. The policy/optimizer resume, while demonstration buffers are rebuilt.
Generated native libraries, fixtures, models and traces live under the ignored
`gpu-d1/learning-runs/remembered-grid/`. Buffers are bounded, only latest/best
checkpoints are retained per arm, and launches require 10 GiB free space.

The simulator change is an opt-in `EXTERNAL_EPISODE_RESET` compile flag allowing
this runner to own fixture reset; ordinary builds retain automatic reset.
Checks compare CPU/CUDA transitions and observed grids, verify unknown terrain
and hidden enemies/stairs cannot leak into observations, assert no repeated
terrain across splits, and verify the invisible remembered threat affects the
global observation while leaving the local crop identical.

Development iterations are retained separately: an initial CNN run without a
persistent expert buffer/augmentation solved the simple pressure fixtures but
failed on most mazes. Its results are not the final demonstration.
