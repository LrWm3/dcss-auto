This plan builds a small D:1 wait simulator and measures completed world transitions per second. It implements a narrower workload than the general [GPU design](DESIGN.md), so the first useful performance result can arrive before support for general player actions or all D:1 mechanics.

The implementation and measurements now live under `gpu-d1`; see [README.md](README.md) and [RESULTS.md](RESULTS.md). The steps below are the original implementation plan. The native exporter/reference build remains isolated from the repository's other simulation projects.

**The proposed first scope is deliberately explicit.** Use an XL1 Human Fighter with fixed native starting stats, scale mail, a buckler, and an ordinary unbranded weapon. The player takes only individual wait actions. Keep real HP, regeneration, EV, armor mitigation, shield behavior, monster attacks, variable monster energy, occupancy, and death. Fixed player equipment and skills are scenario inputs.

Apply the requested exclusions: no gods, player spells, scroll or potion use, nets, evokables, special unrand effects, halo conditions, shouting, auto-explore, or tab targeting. Inert floor items can remain in the exported map but do not enter the timed transition loop.

I recommend these additional cuts for the first measured version:

| Area | Initial restriction | What remains exercised |
|---|---|---|
| Terrain | Floor, ordinary opaque walls, inert stairs; no doors, water, traps, clouds, scripts, or terrain changes | Walls, corners, corridors, and occlusion |
| Monsters | Ground melee creatures with ordinary unbranded attacks; no ranged attacks, spells, constriction, bat behavior, reach, or other special effects | Movement, congestion, scheduling, hit/block/dodge/armor/damage |
| Awareness | All monsters start awake with a fixed hostile target; no sleep, wandering, forgetting, or noise responses | Pursuit toward a known stationary target |
| Player decisions | Wait only; no movement, attacks, inventory changes, stairs, or progression decisions | Incoming combat, regeneration, elapsed time, terminal detection |
| Other effects | No summons, allies, poison, status ailments, displacement, or actor-caused opacity | Fixed-capacity mutable worlds with stochastic combat |

Start with rats, frilled lizards, goblins/hobgoblins with supported gear, quokkas, and jackals. The latter two retain differing speeds and exercise multiple-action scheduling. This is a benchmark population, not a claim to reproduce the whole D:1 spawn distribution. Awake creatures with permanent targets are also an explicit fixture simplification.

Because the player only waits, player weapon damage and movement-triggered pursuit attacks are not exercised. The weapon can be stored in the snapshot without implementing player attack resolution yet. A later movement benchmark must add pursuit attacks before its results can represent native retreat behavior.

With no sound-dependent behavior, omit sound propagation entirely in the first version. With immutable terrain and a stationary player, cache terrain LOS and navigation toward that player. Avoid adding unused sound, dynamic-LOS, or pathfinding computations simply to make the benchmark appear more general. Report these exclusions alongside every headline result.

**1. Confirm and record the build environment.** The inspected hardware is a Quadro RTX 5000 with Max-Q Design, 16 GiB VRAM, compute capability 7.5, and an i7-10750H with six physical cores/twelve logical CPUs. CUDA 12.0 `nvcc` is installed and lists `sm_75` support. The default GCC is 13, while the installed CUDA headers reject GCC newer than 12; `/usr/bin/g++-12` is available.

Compile a small kernel with a configuration such as `nvcc -O3 -std=c++17 -arch=sm_75 -ccbin /usr/bin/g++-12`. Confirm actual kernel execution and GPU event timing before working on Crawl integration. Record compiler/driver versions, source revision and local patches, CPU/GPU identity, build flags, and power/temperature conditions. A functioning driver alone does not prove the complete build works.

Deliverable: a standalone build command and a successful CPU/GPU smoke check. Use CUDA C++ directly; Python can optionally plot CSV results later, but is not required in the simulation or timing path.

**2. Obtain a reproducible, favorable native D:1 layout.** Generate seeded D:1 maps with the native engine in an isolated build. Prefer connected layouts with ordinary walls, open rooms, a few corners/corridors, sufficient floor area, and none of the excluded terrain or runtime scripts. Selection predicates concern supported features and useful work, not measured GPU speed.

Export complete geometry and the native Human Fighter's initial state through a small purpose-built exporter. Native map-statistics facilities can assist selection, but a text map dump is not a complete state snapshot. The source supports seeded generation; its map-statistics mode does not allow multiple iterations with one custom seed, so iterate seeds explicitly rather than assuming one command supplies that corpus.

Preserve the raw native snapshot, its seed, and a source hash. Derive a controlled benchmark fixture with supported monsters, fixed hostility/awareness, and known positions. Record every population/placement/awareness change in its manifest. This avoids spending the project searching for an unusually rare natural seed with exactly the desired enemy roster.

Select at least one starting position with meaningful approach paths and one position suitable for sustained incoming combat. Monsters must have reachable paths; a favorable map must not mean an empty map or enemies trapped behind walls. Export an ASCII rendering plus machine-readable terrain, player, monster, and ruleset records.

Deliverable: one primary native D:1 layout, an unmodified export, documented tactical fixtures, and preferably a second compatible layout reserved for a later sanity check.

**3. Define the workload and accounting before coding the simulator.** One iteration means one alive world executing one explicit wait and all of that wait's monster/environment reactions through the next decision boundary or player death. It is not one kernel launch, one monster action, or one pass over an already dead world.

Use the native elapsed time for an ordinary Human Fighter wait (normally 10 aut) and preserve supported preparation/reaction order. A turn in which the player dies counts once. Before another wait, reset that world from a resident fixture, increment its episode identity, and give it an independent RNG stream. Never repeatedly restore the same RNG state at every death.

The primary rate is `completed_wait_transitions / wall_seconds`, including required on-device resets in the timed workload. Also record monster actions, attacks, blocks, dodges, damage, deaths, resets, and the fraction of turns with actual movement or combat. These diagnostics detect an accidentally trivial or no-op benchmark; collect expensive traces in a separate validation run.

Keep a separately labelled finite-rollout measurement if useful for excluding reset cost. Count only live transitions in that measurement and disclose its changing active-world count. Do not use invulnerability, silently refill HP, or count masked dead lanes to obtain a larger number.

Deliverable: a machine-readable benchmark configuration and an unambiguous counting contract shared by CPU and GPU.

**4. Build the compact CPU transition first.** Use fixed arrays and integer actor IDs, with no allocation or text processing inside a step. Separate shared terrain/rule tables from mutable world data. Store player HP and regeneration accumulators, defensive stats and shield-related state, actor positions/energy/combat descriptors, occupancy, per-world RNG, counters, and terminal state.

Start with a fixed-array version of the native maximum-energy heap. Keep the native threshold, gain/cost rules, repeated actions, and supported event ordering. Port the relevant monster attack, hit/EV, shield, armor, damage, and regeneration formulas from the local source. Cache invariant derived stats; do not substitute constant DPS or a shield probability inferred from only one displayed stat.

Use native PCG operations per world as the initial RNG. Independent RNG ownership is sufficient for this prototype; replacing the generator with Philox is not a prerequisite. Put the supported transition primitives in code that can compile for both CPU and GPU so arithmetic and semantics can be compared without two independently written implementations.

Deliverable: a CPU program that loads the fixture, repeatedly waits, allows death/reset, and produces final state/checksums and activity counters.

**5. Compile geometry and implement the route approximation.** Flatten the native LOS ray data, and compare resulting static visibility against native Crawl for every relevant pair on this small map. Store terrain visibility per origin as needed; the player-origin mask remains unchanged during a wait episode. Monster positions and their visibility in observations still change.

For navigation, precompute a reverse distance field for each fixture's fixed player position and movement profile. A 5,600-cell 16-bit field costs about 11 KiB; all-pairs map navigation is unnecessary for this workload. Select legal next steps from eight neighbors using the field, relevant direction preferences, deterministic random tie breaking, and current occupancy.

Add a small bounded repair search for crowding or a blocked preferred route. If the repair finds no route within its budget, use an explicit wait/retry rule for that monster, and record fallback frequency. This is a declared AI approximation, not evidence that the destination is globally unreachable. Physical moves must remain legal and occur in scheduler order.

Maintain all actors in the fixture, including offscreen ones. Permanent target knowledge is a stated benchmark rule; do not hide it behind a claim of native awareness fidelity.

Deliverable: precomputed geometry tables, a functioning movement/combat loop, and a breakdown of route lookups and fallback searches.

**6. Establish useful correctness checks.** Verify occupancy uniqueness, wall blocking, HP bounds, energy expenditure, reset isolation, and progress under crowding. Use native micro-scenarios to check defensive/combat formulas and action timing. Export or reconstruct all relevant defensive state, not just displayed AC/EV/SH.

Compare native and compact damage, hit, block, death-time, and action-count distributions under matching restrictions. When RNG calls and operation order match, compare individual events. Navigation and any tie-order changes require distributional comparisons rather than an expectation of seedwise identical paths.

For the compact CPU and GPU versions sharing the same specified algorithm and RNG, require matching final states/checksums for identical starts and step counts. Benchmark identical live/reset workloads on both. Run device memory/race checks on small cases where available. Any unsupported mechanic or capacity overflow should fail the fixture validation or report an error; it must not silently remove work.

Deliverable: a short validation report that distinguishes exact compact CPU/GPU agreement from approximate agreement with native Crawl.

**7. Implement the simplest GPU version and get the first rate.** Begin with one thread per world and arrays arranged for contiguous access across worlds. Upload templates, precomputed tables, and initial state once. Execute the whole wait transition inside one kernel, including sequential monster actions within each world. Return counters and checksums after a timed segment, not every turn.

Use fixed capacities appropriate to each fixture rather than the full native monster limit. Count actual and allocated actor slots separately. Do not impose a cap that drops legal monster actions; use a resumable work chunk if needed.

Warm up and test several batch sizes immediately. This is the first performance checkpoint: a validated core, compact CPU baselines, and a GPU batch-size curve. Do not defer it until sound, spells, or every ordinary D:1 monster is implemented.

Deliverable: measured live wait transitions/s, batch latency, and CPU/GPU speed ratios for the initial kernel.

**8. Test the two most relevant optimizations.** Add a warp-per-world implementation in which lanes cooperate on actor scans, occupancy checks, and observations while consequential moves/attacks remain ordered. Give it a suitable actor-contiguous layout. Measure the cost of scalar phases and reductions rather than assuming cooperation is faster.

Separately compare the fixed-array heap with maximum-energy scans/reductions. The native comparator does not define a stable actor-ID tiebreak; using one changes equal-energy behavior. Either preserve the same queue semantics or give both compact CPU/GPU scan variants an explicit common tie rule and validate it as a separate approximation.

Only after profiling, consider additional effects such as packing hot state, reducing observation writes, or bucketing worlds by actor capacity. Do not add expensive combat probability tables unless the small integer formulas are a demonstrated bottleneck.

Deliverable: an ablation table showing which layout/scheduler wins, at which batch sizes and actor counts.

**9. Run a staged benchmark matrix.** First sweep batches `1, 32, 128, 512, 2048, 8192, 32768` on one documented active fixture. Then use the promising batch sizes to sweep actor counts such as `1, 8, 32, 64`, within validated capacities. Some of these are synthetic stress populations on native terrain; label them accordingly.

Use four workload categories:

| Workload | Purpose | Interpretation |
|---|---|---|
| Quiet waiting | No active threats | Lower-cost control; never the headline active-combat result |
| Approach | Monsters traverse rooms/corners before contact | Navigation and occupancy workload |
| Contact combat | Monsters begin in and near attack range | Defense, RNG, scheduling, deaths/resets |
| Mixed phases | Worlds start at different points in valid approach/combat trajectories | Less uniform control flow and a more useful throughput estimate |

All worlds use independent random streams. Report identical-start batches separately from mixed-phase batches, since one map, one action, and synchronized replicas are a favorable cache/divergence case. Approach eventually becomes combat: report its movement/combat fractions or use defined finite approach snapshots, rather than claiming the whole long run remained navigation-heavy.

Measure two execution regimes. In the first, one kernel handles one decision step for the batch; queue successive launches without requiring a CPU readback per step. In the second, each world loops over 64 or 256 waits inside a kernel. The second measures amortized wait-rollout throughput and cannot be presented as the throughput of an agent choosing a new action after every turn. Record batch latency and average live transitions per world as well as aggregate throughput.

Report simulation-only and simulation-plus-observation separately. The observation version must update visible monster data and player state even though terrain visibility is cached. Include no policy-network inference in the headline benchmark; that is an additional future workload.

Deliverable: raw CSV/JSON data and curves for throughput versus batch size, plus actor-count, workload, launch-regime, and observation-cost comparisons.

**10. Time carefully and compare fair baselines.** Use GPU events for device elapsed time and synchronized wall-clock timing for the complete timed segment. Kernel launches are asynchronous, so launch-call duration alone is not execution time; see NVIDIA's [timing guidance](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/#timing).

Exclude compilation, map generation, initial upload, and one-time table construction from steady-state timing, but report their costs separately. Include the death/reset work required to sustain the run. Warm up each relevant configuration, run repeated trials, and report median and spread. Use sufficiently long segments for stable timing, then run longer sustained trials on the leading configurations to reveal laptop thermal/power effects. Do not change device power settings without a reason.

Compare the compact CPU implementation with one worker, six physical-core workers, and optionally twelve logical-CPU workers. Use an isolated native headless reference driver for a matching workload, with UI/logging and the declared excluded mechanics removed from the timing path. Native global state may require separate processes for its parallel baseline. Include native reference step/observation and reset costs transparently; do not compare a GPU transition kernel against native startup or map generation.

A fair report distinguishes `native -> compact CPU` gains from `compact CPU -> GPU` gains. It also distinguishes a one-thread CPU comparison from an all-core comparison. Record activity counters beside performance so a faster result caused by fewer monster actions or no-op worlds is visible.

Deliverable: a reproducible results document containing commands, fixture/build hashes, rates, latencies, activity counters, memory use, variability, and the precise scope limitations. No specific speedup is promised before these measurements.

**11. Expand only if the first result justifies it.** The next useful additions for performance are the other ordinary D:1 enemy behaviors: bats, pythons, endoplasms, dart slugs, and ranged equipment. Add each as a distinct fixture and measure its incremental cost. Then add awareness/noise, mutable blockers, and a movement/attack workload if the goal becomes predicting full decision-loop performance.

The first benchmark answers: “How many independent, physically simulated wait transitions can this machine sustain for a static D:1 melee scenario?” It does not yet answer the throughput of arbitrary D:1 play, player attack evaluation, dynamic maps, or neural policy inference. That limited result is still enough to test whether the compact state representation and GPU batching are worth pursuing.
