# Player visibility screen: 24 enemies, 512 turns

Four fresh seed-0 policies, each trained for 30M decisions. No ogres, stairs, healing, or banking. The same 256 ordinary training layouts and 32 validation layouts × 32 sampled episodes are used throughout. Each evaluation also includes a greedy policy panel.

| Arm | Terrain vision within 9×9 | Enemy information |
|---|---|---|
| global_no_los | Through walls (old reveal rule) | Global live positions, HP, type |
| local_no_los | Through walls | Only enemies inside the 9×9 window |
| local_los | Native wall occlusion | Only enemies visible in that window |
| global_los | Native wall occlusion | Global live positions, HP, type |

`global_no_los` is the requested globally known enemies / LOS-off condition. The complete two-by-two comparison also includes `global_los` to separate terrain occlusion from enemy knowledge. These are new controls at 24 enemies / 512 turns, not direct reuses of the old 40-enemy runs.

## Representation and information boundaries

All arms use identical 502-input, two-layer 128-wide networks, nine actions, and unchanged PPO/reward settings (kill +1, clear +3, death −1, turn −0.001, first-seen floor +0.002). The initial view has no exploration reward. The network retains 40 enemy capacity slots, but only 24 enemies spawn. Input width changes identically for all conditions; no old checkpoint is reused.

Local terrain is unknown=0, remembered wall=−1, remembered floor=+1. An added 81-value channel distinguishes currently visible from merely remembered terrain. The existing remembered ring, frontier, and known-terrain route cue remain. Visibility updates memory and exploration rewards together. No hint routes through unknown floor. Movement masks reject known walls but allow attempts into unknown adjacent cells, so masks do not reveal hidden terrain.

In partial-information arms, both local monster HP images and global monster records are visibility-gated. Records are allocated in discovery order, not preassigned simulator IDs. A hidden enemy supplies no live position/HP/presence information; slots for previously discovered hidden enemies are zero until seen again. This screen does not retain stale last-known positions. Reidentification uses internal simulator identity; the model receives only a previously allocated discovery slot. Total roster size is fixed and can be learned; uncertain roster size is not tested.

In global arms, all living enemies intentionally remain observable even behind walls. These arms are privileged-information controls. Monster wake radius and pursuit rules are unchanged: this changes the player's information, not enemy AI awareness.

## Static visibility cache

Resident map files already contain native-validated 17×17 LOS masks, with ten uint32 words per origin tile. The loader now uploads these tables once per resident map, and the kernel clips the lookup to radius four (9×9). The cache is shared by all parallel episodes: 224,000 bytes per map, 54.7 MiB for 256 training maps. No maps are regenerated. Terrain is static and monsters do not occlude sight. Future dynamic doors/smoke would need a different visibility strategy.

## Diagnostics

Alongside clear/death/timeout, kills, return, and measured training seconds, report actual enemies encountered, living enemies never encountered, encountered enemies still alive, final visible enemies, remembered floor count/coverage, and unseen-versus-encountered survivors conditional on timeout. “Encountered” here means geometrically visible at a decision boundary or physically attacked, even in global-information arms; it is distinct from privileged roster access.

The new diagnostics and knowledge bookkeeping do not consume RNG. Tests replay identical action sequences across arms and require identical combat, deaths, kills, and episode lengths; exploration reward and observations may differ.

Seed 0 is an exploratory screen. Repeat comparisons across training seeds before claiming a reliable effect. Fixed evaluation panels have been reused for development; they are validation, not an untouched final test.

## Run and verify

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision-v1/scripts/run_ring_ablations.py \
  --smoke --output gpu-d1/learning-runs/vision24-512-smoke
gpu-d1/.venv/bin/python gpu-d1/branches/vision-v1/scripts/test_vision.py \
  gpu-d1/learning-runs/vision24-512-smoke
gpu-d1/.venv/bin/python gpu-d1/branches/vision-v1/scripts/run_ring_ablations.py \
  --steps 30000000 --seeds 0 --output gpu-d1/learning-runs/vision24-512-screen-30m
```

The sequential runner retains one latest/resumable and one best checkpoint per arm, with a 2 GiB suite cap and 5 GiB free-space reserve. Map data are shared rather than copied. Milestone evaluations: 0, 1M, 3M, 10M, 30M decisions; latest resume checkpoints every approximately 1M.

## Validation and launch

All four end-to-end smoke jobs completed. Semantic tests and 8,400 CPU/CUDA world steps per arm passed (33,600 total), including matched combat and visibility-based exploration rewards. Independent Python checks matched the local observation to the packed mask in all arms; all 9,710,400 visibility pairs in six available native exports matched the cache.

The 120M-total-decision queue is running in the listed order. Log: `results/vision24-512-screen-30m-console.log`; plan: `results/vision24-512-screen-30m-plan.json`; suite: `learning-runs/vision24-512-screen-30m`. Validation log: `results/vision24-512-validation.txt`.

Post-run review: [findings and independent frontier audit](reviews/vision/REVIEW.md). The four trained configurations passed; incompatible legacy feature combinations are now rejected at compile time.


## LOS-gated monster waking follow-up (2026-09-15)

Isolated implementation: `branches/vision-awareness-v1`. Sleeping monsters now
wake only when the player is within Chebyshev distance six **and** visible in
the cached native LOS mask from the monster's own square. Already-awake pursuit
remains unchanged; player vision remains radius four. No other task, observation,
reward, or PPO setting changes. The original four-arm experiment is preserved.

Fresh training: local enemy information + wall-blocked vision, 24 enemies,
512 turns, seed 0, 30M decisions, 256 training layouts, the same 32-map validation
panel. Suite: `learning-runs/vision24-512-los-awareness-30m`; console:
`results/vision24-512-los-awareness-30m-console.log`. Metadata explicitly records
`monster_wake_los: true`, and the native library name includes `wake-los`.
Compare against the original `local_los` final clear rate of 21.875% (1024 episodes).
This tests a detection-rule change, not whether additional training alone helps.

Validation: end-to-end smoke passed, native floor-pair checks cover occluded,
unobstructed and out-of-range detection with monster-origin LOS across two maps;
transition checks cover sleeping/waking behavior. Existing knowledge-leak,
reward-accounting, active-mask tests and 8,400 CPU/CUDA world steps passed.
The runner retains bounded checkpoints with a 2 GiB cap and 5 GiB free reserve.
