# Cached exact remembered geometry

First screen: native 80×70 maps, unchanged 15×15 local crop, enemy-free
navigation, 1024-turn evaluation deadline. No route distances, frontier arrows,
connectivity labels, or unobserved terrain are supplied to the policy.

## Representation

The global input is four exact remembered terrain categories plus discovered
stairs. A lossless 2×2 space-to-depth rearrangement feeds a small dilated CNN.
Its output is an 8×35×40 spatial feature grid. A learned projection of the
flattened grid supplies 64 global features; a 3×3 patch sampled at the player's
position supplies 72 nearby features. Normalized exact player coordinates are
supplied separately. A small readout maps these to a 96-dimensional residual.

The existing coarse global branch is retained, and the new residual starts at
zero. This preserves the source checkpoint's predictions before training.
This is an additive capacity/information experiment, not a clean replacement
of the coarse representation or a parameter-matched comparison. Exact player
coordinates are also new information compared with the previous coarse bin.
The input rearrangement preserves every tile; learned CNN features and the
global projection are still compressions, without a guarantee of preserving
connectivity or learning planning.

Inference stores the spatial features and global projection separately for each
environment. It recomputes them whenever any remembered terrain category or
discovered stair changes. Player movement alone does not invalidate this cache;
visiting a previously unvisited tile does. Resets discard the cache. Encoder
parameter version changes invalidate it. There is no deliberately stale map
encoding, and dynamic tactical information stays in the local branch.

Training replays raw observations and recomputes all learned features with
current weights and gradients. The inference cache is not used during gradient
updates. All policy parameters remain trainable.

## Checks and initial speed

`check_native_cached_exact.py` verifies source parity, lossless rearrangement,
cached/uncached rollout parity, movement-only cache reuse, invalidation after
encoder updates, reset, and nonzero map-encoder gradients. On 96 steps × 32
worlds, cached and uncached policies had zero greedy action disagreements;
maximum logit difference in the final check was 0.0078125 with AMP and varying
convolution batch sizes (within the relative/absolute comparison tolerance).
The teacher-driven replay refreshed 38.54% of map slots.

The initial eager AMP policy-only replay measured approximately 2,147 decisions/s
uncached and 2,103 cached. This is **not a speed improvement**. It includes
preprocessing and cache management, but excludes environment stepping and
training updates, so it is not PPO throughput. These trajectories include
finished slots; the refresh fraction is not an active-only episode statistic.

## Learning screen

`native_cached_screen.py --name native-cached-exact-seed0 --updates 2000`
uses the existing middle-route balanced DAgger screen: same starting curriculum
checkpoint, seed 0, 50% expert/50% learner-buffer loss, category balancing,
16 burn-in and 16 gradient steps, 1e-4 learning rate, and validation selection
every 500 updates. Collection ends at 512 steps; evaluation allows 1024.
The historical balanced/coarse screen supplies the comparison. This is a short
imitation/DAgger experiment, **not PPO**. It retains the known short recurrent
burn-in limitation to match that control.

Two checkpoints per run are retained (latest and validation-selected), not every
intermediate checkpoint. Evaluation uses held-out layouts.

## Completed result

The first attempt was interrupted by machine shutdown before saving a checkpoint;
the restarted experiment completed all 2,000 updates. The selected checkpoint
was at 500 updates. No AMP overflow updates were skipped. Training plus data
collection took 262.1 seconds, excluding evaluation, versus 188.5 seconds for
the historical balanced coarse-only screen (approximately 39% longer).

Test success percentages, 128 episodes per category on 32 held-out layouts:

| Policy | Middle known stairs | Middle exploration | Longer known stairs | Longer exploration |
|---|---:|---:|---:|---:|
| Starting curriculum checkpoint | 64.84 | 69.53 | 31.25 | 56.25 |
| Coarse-only balanced continuation | 62.50 | 69.53 | 35.16 | 50.78 |
| Cached exact-map addition | 68.75 | 52.34 | 34.38 | 35.94 |
| Same selected model, exact residual erased | 68.75 | 60.94 | 40.62 | 43.75 |

This implementation did not improve overall navigation. Removing the learned
exact-map contribution improves three of four test categories. That is evidence
that its learned contribution is harmful in this screen; it does not establish
that exact remembered geometry cannot support a better policy. This is one seed,
and the erased-input intervention is not a separately trained alternative.

The initial 61.46% apparent reuse included finished environment slots. Among
active decisions on the benchmark teacher trajectories, **85.86% require a map
refresh**, leaving only 14.14% that can reuse the map encoding. Discovery and
first-time visitation both invalidate this exact cache. Thus substantial savings
were unlikely on this trajectory distribution, even with free cache management.

Final performance numbers are in `results/native-cached-exact-seed0.json`, under
`replay_benchmark`. The benchmark warms each policy and repeats the same
96-step, 32-environment trajectory 20 times. The exact variants use a compiled
readout; the coarse reference uses its established CUDA-graph implementation.
Consequently the coarse/exact comparison includes implementation differences,
whereas exact cached/uncached measures the cache tradeoff directly. None of these
are PPO decisions/second. The cache has not demonstrated a throughput win.

| Policy-only replay | Decisions/second |
|---|---:|
| Coarse reference, optimized CUDA graph | 73,236 |
| Exact addition, compiled readout, uncached | 12,696 |
| Exact addition, compiled readout, cached | 10,520 |

Caching was about 17% slower than uncached exact processing in this replay.

Before the final benchmark, redundant coarse-map preprocessing was removed from
the new policy. A parity check verifies identical prepared inputs to the version
used for training; this change does not require retraining. The final correctness
check also retains zero greedy disagreements between cached and uncached paths.

The result argues against adopting this implementation. A next design would need
to address both learning useful global spatial features and the low reuse rate,
for example by separating persistent terrain geometry from rapidly changing
visit information. That alternative has not been tested here.
