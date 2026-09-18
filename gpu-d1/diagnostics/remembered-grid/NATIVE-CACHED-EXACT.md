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
maximum logit difference was 0.001953125 with AMP and varying convolution batch
sizes. The teacher-driven replay refreshed 38.54% of map slots.

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
intermediate checkpoint. Evaluation uses held-out layouts. Results and timing
will be recorded after completion, including selected-policy evaluation with
the exact-map residual erased to check whether the new branch contributes.
