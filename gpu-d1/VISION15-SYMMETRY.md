# Rotation/reflection training: ordinary versus one-third clumped

Train fresh seed-0 policies for 30,015,488 decisions each, with the same starting
weights, 256 training layouts, 32 validation layouts, PPO settings and rewards as
the earlier ordinary and clump-trained 30M models. No ogres or travel. 24 enemies,
2048 turns, 15x15 wall-blocked vision, LOS wake, remembered ring/frontier/route,
seen-floor scalar; +1 kill, +3 clear, -4 death, +.002 new floor, -.001 turn.
Ordinary placement in one arm; one-third of reset episodes clumped in the other.

## Treatment

One of eight uniformly selected D4 camera orientations (four clockwise rotations,
with or without horizontal reflection) per episode. Transform all spatial
observation components, legal action masks, and translate chosen directions back
before native stepping. Wait and nonspatial features are unchanged. Rotate enemy
coordinates after undoing their /80,/70 scales; preserve enemy slot order.
Transform frontier coordinates, unknown direction and route cue, rather than
recomputing them under different tiebreaks.

Absolute position is rotated about the actual tile-grid center (39.5,34.5) in
physical tile units, then encoded with the existing /80,/70 scales. Because the
map is rectangular, quarter-turns can put these two scalars slightly outside
[0,1]; this is intentional and unclipped. This makes the transform invertible
and spatially consistent without adding map-size inputs or changing identity
observations. Native positions and map geometry never change.

Separate augmentation RNG leaves the seeded network initialization unchanged.
Store the transformed observations/actions/log probabilities actually used for
play in PPO buffers; do not resample transforms inside optimization epochs.
Save orientation IDs, augmentation RNG and native observations/masks alongside
native worlds and optimizer state for exact resume.

The simulator is byte-identical to the clumps branch. Its directional tiebreaks
remain, so this is camera augmentation, not a claim that native dynamics are
exactly equivariant. Augmentation encourages, but does not enforce, policy symmetry.
No eight-view ensemble or extra policy passes are used.

## Checks and evaluations

Independent feature transform reference, inverse transforms, identity equality,
action/mask permutations, and 64 native worlds x 256 steps verify behavior parity
under translated actions. Check orientation stays fixed within episodes and
checkpoint replay includes both RNGs. Both variants pass a tiny end-to-end PPO
smoke run and preserve the historical initial weights.

Validation is always in the ordinary identity orientation, with ordinary enemy
placement, same 32 layouts x 32 episodes and seeds as earlier runs. Report sampled
and greedy metrics, training seconds excluding evaluation/setup/I/O, and total
pipeline wall time. Do not add rotated validation episodes as independent evidence.

After training, rerun unchanged three-enemy hallway, six-enemy hallway, diagonal
pocket, distant pockets (4/6 steps), mirrored/rotated forced-route pockets, and
static single-enemy pocket action probabilities. All prior HP/roster/rotation
sweeps and 512 combat seeds per condition remain. Natural and forced-retreat arms
separate reaching safety from defending it. Scripted-control results must match
historical results exactly. Compare with the existing unaugmented 30M checkpoints.
These are one-seed synthetic competence checks, not a claim of reliable superiority.

`DCSS_DIAGNOSTIC_MODELS` can point to a JSON file containing ordinary/mixed model
paths and a mandatory safe output prefix. Defaults retain historical behavior;
this pipeline uses `d4-` and never overwrites historical diagnostic results.

## Run

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-symmetry-v1/scripts/run_experiment.py
```

Outputs: `learning-runs/vision15-symmetry-30m` (2 GiB budget, 5 GiB free reserve),
`results/vision15-symmetry-*.json`, and `results/d4-*.json`. Existing ignore rules
exclude checkpoints, compiled libraries, generated maps and logs. No corpus copies.

Timing note: requested greedy retreat diagnostics ran on the same GPU during part
of the clumped D4 run (roughly 02:06–02:10 local on September 16). Recorded training
seconds include any contention during that overlap; do not interpret the two D4
runs' throughput difference as a clean augmentation/placement benchmark.

## Completed seed-0 results

Both augmented policies reached 30,015,488 decisions. The full pipeline completed
in 977.51 seconds (16.29 minutes); initialization, native-source and scripted-control
parity checks passed. Sampled evaluation uses identity orientation, no ensembling.

| Training placement | Ordinary clear rate before → D4 | Training seconds before → D4 |
|---|---:|---:|
| Ordinary | 78.71% → 80.96% | 220.03 → 229.62 |
| One-third clumped | 78.03% → 77.34% | 267.63 → 300.22 |

Timing caveat above applies. This single training seed cannot establish a robust
performance advantage or isolate augmentation from training-run variation.

Natural tactical clear rates, tough roster and player HP 12/18, pooled rotations:

| Geometry | Ordinary before → D4 | Clumped before → D4 |
|---|---:|---:|
| One-step hallway (3 enemies) | 92.24% → 88.18% | 93.31% → 93.90% |
| Three-step hallway (6 enemies) | 7.42% → 22.80% | 51.81% → 35.60% |
| Two-step diagonal pocket | 35.01% → 33.54% | 56.40% → 52.20% |
| Four-step diagonal pocket | 17.53% → 19.14% | 30.57% → 34.18% |
| Six-step diagonal pocket | 5.96% → 9.18% | 19.29% → 21.83% |

The clearest change is defending the six-step pocket after the full retreat is
supplied. Ordinary-model clears rise 63.57% → 82.08%, with contact waiting falling
34.55% → 5.12%. Rotational clear range narrows from 28.13–83.59% to 81.25–83.98%,
close to the scripted retreat-and-fight control's 83.01% pooled clear rate.
The model is much better at defending these pockets but still rarely reaches
them on its own.

Clumped-model forced-route clears rise 63.48% → 69.48%, with contact waiting
38.76% → 30.47%. The worst pocket orientation changes from NE to SW: SW contact
waiting is now 62.94%, and its clear rate 38.48%, versus 75.20–83.59% elsewhere.
Augmentation therefore has not consistently removed directional behavior.

The static one-enemy test looks improved: maximum waiting over orientations in
the kind-3, full-enemy-HP, player-12-HP case falls 39.06% → 17.68% ordinary and
40.27% → 9.23% clumped. That improvement does not guarantee reliable defense in
multi-enemy rollout states; report both rather than treating the static test as
sufficient evidence of a fix.

Unaugmented training seeds 1 and 2 are queued/running separately, with the same
complete tactical suite, to assess natural seed-to-seed directional variability.
