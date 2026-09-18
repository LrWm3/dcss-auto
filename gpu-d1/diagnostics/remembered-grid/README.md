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

## Faster execution

See [the optimization report](PERFORMANCE.md) for the cropped-decoder, mixed-precision
and compiled execution path, full-map compute measurements, and navigation regressions.
The trained spatial checkpoint can be reused without reducing the observation
or model capacity. Packed and narrower variants are experimental controls.

The [cached map encoder experiment](CACHED.md) separates player-independent terrain encoding from a small actor, compares refresh intervals, and tests frozen-encoder PPO. It is faster in network benchmarks but currently weaker at known-stair navigation.

The [position-aware compact representation screen](COMPACT.md) compares cached-map attention, learned coarse blocks, and a five-count-per-block global summary, including equal-budget navigation results and full-map compute estimates.

## Compact count follow-ups

[Finer count blocks and observed boundary crossings](COUNT-REFINEMENTS.md) reports the completed seed-0 comparison, full-size compute estimates, and a diagnostic of the original model's dependence on global visited history.

[Visited-tile count follow-up](VISIT-COUNTS.md) tests a sixth global count channel at both 4x4 and 2x2 resolution. Both seed-0 runs and their held-out/compute evaluations are complete.

[Exact visited-bit follow-up](VISIT-BITS.md) preserves the four within-block visited positions at 2x2 resolution. The completed seed-0 run improves known-stair navigation but remains mixed on longer exploration.

[Two-scale symbolic maps and recurrence](SYMBOLIC.md) compares a 15x15 categorical local crop plus a 16x16 fractional global map, with feed-forward versus GRU sequence training. The GRU navigates much better but paired-goal and erasure tests show weak reliance on its global map.

[Symbolic GRU optimization](SYMBOLIC-OPTIMIZATION.md) profiles the network, adds equivalent crop-first preprocessing and fused recurrent sequence training, and measures optional mixed-precision/precomputed-input configurations.

[minGRU screen](MINGRU.md) replaces the symbolic policy's recurrent core with a numerically checked affine-scan minGRU, comparing navigation behavior and full-map network cost with the optimized GRU.

[Fused minGRU scan](MINGRU-SCAN.md) validates a custom forward/backward GPU scan, separates recurrent versus whole-policy cost, and corrects the earlier AMP benchmark that omitted encoder/core gradients.

[Encoder optimization](ENCODER-OPTIMIZATION.md) tests bypassing identity pooling and channels-last CNN execution, using complete training gradients and unchanged saved GRU weights.

[Compiled execution and CUDA graphs](EXECUTION-OPTIMIZATION.md) separates encoder/head compilation from graph capture, checks live input and recurrent-state handling, and benchmarks both factors against the optimized GRU.

[First symbolic recurrent PPO run](SYMBOLIC-PPO.md) continues the supervised GRU with actual on-policy learning, sparse exit/death rewards, sequence-preserving updates, and measured pipeline throughput.

[Symbolic PPO degradation investigation](SYMBOLIC-PPO-DEGRADATION.md) separates shared critic gradients, policy updates, and bootstrapped advantage targets, with checkpoint and same-data gradient audits.

[Durability and full-size progression](SYMBOLIC-PPO-SCALE.md) tests corrected PPO through 3M across two seeds and gates progression to native 80x70 navigation layouts.

[Native-scale demonstration curriculum](NATIVE-CURRICULUM.md) trains progressively longer routes on native geometry before a conditional PPO handoff.

[Middle-distance remedies](NATIVE-REMEDIES.md) audits demonstration coverage and compares mixed-controller training, balanced pure-learner DAgger, and an exact remembered-map residual encoder.

- [Full-history recurrent replay comparison](NATIVE-HISTORY-REPLAY.md)

- [Observation-restricted deterministic teacher](OBSERVATION-TEACHER.md)

- [Cached exact remembered geometry](NATIVE-CACHED-EXACT.md)

- [Spatial processing versus analytical routing](ROUTE-COMPARISON.md)
