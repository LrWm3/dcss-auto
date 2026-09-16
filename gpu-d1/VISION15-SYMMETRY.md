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
