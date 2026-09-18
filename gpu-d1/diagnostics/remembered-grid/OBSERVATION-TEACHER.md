# A teacher restricted to the symbolic policy's information

Build and evaluate a deterministic navigation program using only a subset of
the existing learner's prepared inputs. This is a feasibility diagnostic, not
new model training. All experiments are enemy-free, native 80x70 navigation,
with a 1024-turn deadline and the existing disjoint layout splits.

## Input contract

The C++ planner receives only:

- 15x15 player-centered terrain categories and discovered stairs;
- 16x16 global terrain fractions, discovered-stair presence, and player-bin;
- the same 19-action legality mask used by the model.

The Python adapter calls the learner's exact `FastSymbolicPolicy.prepare`
function, then passes only the above arrays across the C ABI. No neural network
weights are executed. Tactical features and HP/time scalars are available to
the learner but unused by this enemy-free teacher. The planner cannot access
raw global terrain, exact player XY, map/scenario IDs, simulator memory,
precomputed distances, existing teacher labels, or fixture walk histories.
There are no simulator callbacks or file reads inside the C++ planner.
Fixed map dimensions and movement rules are public task constants.

## Algorithm

Use exact local BFS on remembered traversable cells. If a discovered stair is
locally reachable, walk toward it; use the exit action on a stair. Otherwise
use coarse-grid Dijkstra to favor a region containing discovered stairs, or a
region near unexplored terrain. Coarse adjacency is an optimistic hypothesis,
not an assertion that a passage exists. Fully known wall-only bins are excluded.

Exact within-bin player location is unavailable. Average coarse guidance over
all coordinates compatible with the observed player bin; never substitute the
simulator's true coordinates. Candidate local actions follow known-floor paths
to the crop boundary or make a single attempt at an unknown neighboring tile.
The local search does not treat arbitrary unknown tiles as traversable paths.
When exploring, prefer nearby local frontiers; use global guidance for
backtracking when none remain locally.

Compare two variants of this one planner:

- **stateless**: recompute from the current observation alone;
- **history**: additionally count previous choices at identical local/coarse
  observations and visits to coarse bins. Penalize repeating the same choice
  at a repeated observation; prefer less visited exploration regions.

History consists only of previous allowed observations and the program's own
fully deterministic choices. It does not read action outcomes or assume that
a requested move succeeded. These choices are functions of observation history;
no odometry or previous-action sensor is supplied. Histories reset at episode
boundaries. This information restriction does not match the learned model's
computational resources or its 128-dimensional learned memory: the program has
hand-written search and an explicit dictionary. It also does not establish that
its actions are uniquely correct or optimal.

The existing exact remembered-map BFS teacher is evaluated separately as a
reference. That reference has richer map information than either new variant.

## Checks and evaluation protocol

`check_observation_teacher.py` checks a local stair route, exit selection,
action masking, reproducibility after memory reset, and isolation of independent
world histories. The narrow C ABI provides the input boundary; no new inputs
are added to the neural policy. Evaluation metadata is recorded outside the
planner and is never passed to it.

Both variants were specified before validation. No planner parameters or logic
were changed after viewing validation outcomes. Freeze the same implementation
for held-out test evaluation; record its SHA256 in each report. Validation has
64 cases per category on 16 maps; test has 128 per category on 32 disjoint maps.
These are deterministic controller evaluations, not stochastic training seeds.

```sh
python check_observation_teacher.py
python observation_teacher.py --split validation
python observation_teacher.py --split test
```

The C++ helper compiles with the local C++17 compiler and runs on CPU. The
existing simulator and observation preprocessing run on GPU. Reports contain
per-scenario outcomes and evaluation wall times. No demonstrations/checkpoints
are produced, and no training job is queued by these scripts.
