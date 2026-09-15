# Small randomized ogre-pressure curriculum, seed 0, 50M per arm

## Question and comparisons

Does adding targeted avoidance situations improve behavior on new pressure layouts, and does it help or hurt ordinary floor clearing? Two fresh 50M-decision runs share the simulator, observation schema, optimizer, rewards, evaluation panels and seed:

| Arm | Training resets | Evaluation panels |
| --- | --- | --- |
| ordinary_only | 100% ordinary | Ordinary, pressure training layouts, held-out pressure layouts |
| pressure10 | 90% ordinary / 10% pressure, sampled at each reset | Same three panels |

Evaluating pressure scenarios never updates the policy. Therefore ordinary_only supplies the test-only exposure condition, and pressure10 supplies train-and-test exposure. An extra training-only arm would learn identically to pressure10 and adds no useful contrast. The 50M budget is total player decisions per arm, not 50M ordinary decisions plus extra pressure experience. Short pressure episodes may occupy much less than 10% of decisions; that fraction is measured rather than assumed.

## Scenarios

There are 32 training and 16 held-out pressure layouts, split between narrow loop detours and wider pillar rooms. Each is an approximately 16–23 by 12–18 playable bounding box embedded in the existing 80×70 canvas, preserving input coordinates and observation dimensions. Randomized dimensions, corridor widths, translation and reflection vary the geometry. Starts place `@` (player) and `s` (required ordinary monster) on opposite sides of an optional `q` (ogre), with an alternative route around the obstacle. Both initially sleeping and initially awake ogres are included, with energy phases 70 or 75. ASCII previews accompany each map.

Each pressure episode has exactly one living required monster (slot 0, ordinary type 0, 8 HP) and one living optional ogre (slot 24, 48 HP). Other slots are inactive. Clearing requires killing the ordinary monster only. Ordinary episodes retain 24 required monsters and two optional ogres. Player statistics, energy-system combat, wake radius, nine actions, 1024-turn deadline, +1 ordinary kill / +3 clear / -1 death / -.001 turn / +.002 new-floor rewards are unchanged. Close pressure starts deliberately relax the ordinary ogre spawn distance of at least 12 tiles; this is controlled distribution shift.

The full required/optional input remains present in both arms. Baseline ogre feature bits remain zero: no new explicit awake, speed or combat-stat inputs. Observation width remains 741. Live monster count and geometry naturally differ, but no group, family or scenario ID is exposed to the policy.

These are two restricted geometry families, not a broad test of general strategic reasoning. Training and held-out layouts have disjoint canonical geometry hashes after removing translation and accounting for reflection/rotation. Their generation grammar is shared. Held-out results are diagnostic validation, not an untouched final benchmark.

## Labels and statistics

Native transition outputs, captured before auto-reset, include a pressure/ordinary label, resident scenario index and initial ogre count. They are separate from observations. Metadata maps indices to stable scenario IDs, family and split.

Each checkpoint separately reports:

- `sampled` / `greedy`: ordinary validation, 32 maps × 32 episodes.
- `pressure_train`: sampled evaluation on 32 training pressure maps × 32 fresh episodes.
- `pressure_heldout`: sampled evaluation on 16 held-out pressure maps × 32 episodes.

Each panel includes clear/death/timeout rates, ogre-inflicted fatal blows, kills, damage, new wake events, living/awake ogres at termination, turns adjacent to or within three tiles of an awake ogre, and clears leaving the ogre(s) alive. Per-map and per-family summaries remain separate. The actual initial ogre count is used for denominators (one in pressure, two in ordinary). Wake metrics count *new* wake events; initially awake ogres do not create a wake event. Geometry/initial-condition metadata accompanies scenario IDs for interpretation.

`training-groups.json` tracks ordinary/pressure decision counts, completed episodes, clear/death counts, ogre deaths/kills/damage, wake events, awake-ogre exposure turns, shaped return and completed episode turns. All are also broken out by scenario. These are cumulative counters, saved/restored with the optimizer and live worlds. Return/exposure/decision totals include in-progress episodes; terminal totals count only completed episodes. `comparison.json` summarizes the final matched comparison without pooling distributions.

## Implementation and validation

The new `ogre-pressure-v1` snapshot inherits the fast BFS, small block launches and inactive-world evaluation path. Geometry and all-pairs distance fields are precomputed once. The native reset selects an ordinary or pressure map and installs the pressure actors when applicable; no CPU-side scenario construction occurs per training step. The LOS array in generated map files is zero-filled because this particular ring toy simulator does not read native LOS tables. These maps must not be used as native-Crawl LOS fixtures.

Validation completed:

- 48 unique canonical geometries; every layout has a static route outside a two-tile ogre exclusion zone.
- A scripted controller using full geometry cleared all 48 starting scenarios without ogre damage under one fixed combat seed. This demonstrates a possible solution for each, not guaranteed avoidability under every random combat outcome. It is a feasibility witness only: never a teacher, policy input or reward source.
- Pressure roster, one-kill goal, label/index outputs and CPU/CUDA transition parity checked.
- A 2,048-world reset test sampled 10.4% pressure episodes for the 10% mixture; the zero-mixture control selected none.
- Ordinary-only trajectories and observations match the previous simulator over 2,400 world turns.
- Both arms passed end-to-end smoke training/evaluation. Interrupted mixed-arm resume checks model, optimizer, worlds, observations, RNG and cumulative training counters.

## Queue and reproduction

The suite runs after the already queued no-optional-label ablation completes, preserving that experiment independently. Both arms start from scratch; neither continues the 150M model. Evaluation milestones are 0, 1M, 3M, 10M, 30M and 50M. Latest/best checkpoint retention stays bounded by the 2 GiB runner budget; generated fixtures are shared rather than copied into run outputs.

From the repository root:

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/ogre-pressure-v1/scripts/queue_after.py --after-suite gpu-d1/learning-runs/ogre2-no-optional-label-50m --variants ordinary_only,pressure10 --seeds 0 --steps 50000000 --output gpu-d1/learning-runs/ogre-pressure-screen-50m
```

Repeat that same command to resume, including `--after-suite`. The queue refuses to start if its predecessor stops unfinished. Native sources, runner sources, pressure descriptors, geometry files and ordinary corpus hashes are pinned in the manifest.

Primary comparison: held-out pressure clear rate at 50M. Also report ordinary clear rate, held-out ogre deaths and clears with the ogre alive, actual pressure decision fraction, training seconds and per-family differences. A gain on pressure training layouts alone suggests familiarity; a held-out gain supports transfer within these geometry families. A pressure gain with worse ordinary clearing is a tradeoff. One seed is a first screen, not a precise or reproducible treatment-effect estimate.

Progress: `gpu-d1/results/ogre-pressure-screen-50m-console.log`. Final summary: `gpu-d1/learning-runs/ogre-pressure-screen-50m/comparison.json`.
