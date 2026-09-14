There is a plausible GPU port of D:1: a separate, compact stochastic simulator, with the existing Crawl engine used to compile content and check behavior. The main source of parallelism should be independent worlds or rollouts. Preserve the order of consequential events inside each world. Precomputation and a smaller state representation should do more of the work than simplifying combat.

This is the broader source-backed design. A narrower wait-only prototype has now been implemented and measured: see [README.md](README.md) and [RESULTS.md](RESULTS.md). It uses the checked-in `crawl-0.35/crawl-ref/source` and ignores the other simulation/training projects in this repository. The inspected machine has a Quadro RTX 5000 with 16 GiB of GPU memory; the sizing examples below remain calculations for the broader design.

The scope is D:1, no gods, prebuilt maps and initial placements, and explicit player decisions. There is no auto-explore, travel planner, tab targeting, UI, message formatting, save system, or Lua interpreter in the GPU runtime. A move can still bump-attack, but the simulator does not choose a target or route for the player. Both independent training games and candidate-action rollouts use the same transition function.

**What D:1 actually requires.** The ordinary population table includes twelve monster types: bat, rat, frilled lizard, ball python, goblin, kobold, hobgoblin, endoplasm, dart slug, quokka, jackal, and gnoll. This is from the local [population table](../crawl-0.35/crawl-ref/source/mon-pick-data.h), rather than a generic description of early Crawl.

Several of those already require meaningful mechanics. [Bats](../crawl-0.35/crawl-ref/source/dat/mons/bat.yaml) have speed 30 and bat behavior; [ball pythons](../crawl-0.35/crawl-ref/source/dat/mons/ball-python.yaml) have speed 12, amphibious movement, and constriction. Quokkas and jackals also have nonstandard speeds. [Endoplasms and dart slugs](../crawl-0.35/crawl-ref/source/mon-spell.h) have Freeze and Slug Dart. [Monster equipment generation](../crawl-0.35/crawl-ref/source/mon-gear.cc) includes weapons and kobold stones, with depth restrictions that should be resolved by the exporter.

The ordinary population is not the complete content boundary. [Arrival vaults](../crawl-0.35/crawl-ref/source/dat/des/arrival/twisted.des) contain other monsters, including enclosed displays and neutral creatures, plus fog-machine markers. A creature behind a barrier may still be relevant to noise, targeting, terrain changes, or spells. Also, D:1 does not imply a melee-only player: Summoner, Forgewright, Artificer, species abilities, initial equipment, and accessible loot expand the required effects substantially.

The content compiler should therefore produce a manifest for each exported scenario: terrain features, monster and item types, brands, reachable player abilities, status effects, scripted events, and capacity requirements. Compute the closure through effects: a supported spell that summons a creature also requires that creature's behavior. Reject or route unsupported scenarios explicitly and report their frequency. Removing exceptional vaults is a useful initial corpus restriction, but is not full D:1 support. Removing gods follows the requested scope; assuming a fixed species/background would be an additional restriction.

Ordinary pre-Orb D:1 does not need ambient random monster spawning: [spawn_random_monsters](../crawl-0.35/crawl-ref/source/mon-place.cc) returns outside the relevant special branches and Orb run. Summons and any scenario-specific spawns still require runtime support.

**Compile immutable content once and share it between worlds.** Use the native engine offline to export generated geometry, initial monster stats and gear, item identities, starting characters, and rule tables. Precompute candidate cells for teleports, summons, and placement; validate dynamic eligibility when those events occur. Random candidate lists can be prepared in advance, but a destination chosen before occupancy is known is not a valid replacement for a state-dependent placement rule.

Split each scenario into a shared immutable template and a mutable world. The template holds terrain, static topology, compiled visibility/navigation data, item definitions, and initial-state records. Each world holds player state, monster state, occupancy, doors and changed terrain, mutable items, clouds, timers, discovered information, and RNG identity. Initial loot can be shared; quantities, pickup/drop locations, identification, charges, and equipment changes cannot.

Use fixed arrays, integer IDs, bit flags, and explicit effect records. The native [monster](../crawl-0.35/crawl-ref/source/monster.h) has a path vector and a map of enchantments; [player](../crawl-0.35/crawl-ref/source/player.h) includes extensive state and collections outside this scope. Copying those object layouts to device memory would retain much of the problem. Compile the relevant rule subset into small functions and tables, with no runtime allocation, strings, virtual actor dispatch, or generic property dictionaries.

For a thread-per-world kernel, fields such as `monster_hp[slot][world]` give neighboring lanes contiguous accesses. For a warp-per-world kernel, use tiles that make consecutive monster slots contiguous to the warp. These are different layouts; choose after benchmarking, rather than assuming one layout serves both. Keep cold inventory/progression data separate from frequently touched positions, HP, energy, and behavior. Cache derived combat stats and invalidate them on equipment, skill, level, or status changes.

Start with capacity classes such as 32, 64, and 128 actors, including summons, and separate classes for item/cloud/event capacity. Those numbers are candidate buckets, not measured D:1 maxima. Determine coverage from exported scenarios and runtime stress tests. Overflow must produce an explicit continuation or unsupported result, never silently delete an actor or discard an event.

**The main algorithm substitutions are these.**

| Native work | Proposed GPU representation or algorithm | Fidelity and limitation |
|---|---|---|
| Object graphs, dynamic properties, effect callbacks | Fixed arrays, tagged effects, precompiled rule functions | Can preserve supported behavior; the content manifest defines coverage. |
| Monster priority queue | Fixed-array heap first; benchmark a masked maximum-energy scan/reduction | Preserve sequential actions. A different tie rule is an approximation. |
| Monster A* searches and waypoint vectors | Static navigation lookups, eight-neighbor scoring, bounded dynamic repair | Route preferences and congestion behavior are approximations to validate. |
| Runtime LOS structures and invalidation | Native ray geometry flattened to bitsets; cache unchanged terrain results | Can preserve corner and partial-opacity rules. |
| General beam machinery | Precompiled ray candidates and short bounded ray walks | Preserve blocking, range, target order, and relevant hit effects. |
| Whole-grid noise propagation | Precomputed acoustic transfer data evaluated at actor locations | Approximate source competition, bends, and mutable terrain explicitly. |
| Combat and regeneration formulas wrapped in general game logic | Compact integer formulas; optionally small conditional probability tables | Retain stochastic outcomes and rounding, rather than average damage. |
| Global RNG selection and stateful call streams | Per-world PCG baseline; optionally keyed Philox event streams | Philox changes seedwise trajectories, not the intended marginal distributions. |
| Rejection loops for destinations | Static candidate sets plus dynamic masks and rank selection | Exact only if candidate weights, retries, and fallback semantics match. |

**Turn timing should survive the rewrite.** In [world_reacts](../crawl-0.35/crawl-ref/source/main.cc), player/environment reactions, noise, monster actions, deferred effects, elapsed-time updates, clouds, and post-monster reactions occur in a particular order. Preserve the relevant phases instead of reducing a turn to “player moves, every monster moves, apply damage.”

In [_monster_add_energy and handle_monsters](../crawl-0.35/crawl-ref/source/mon-act.cc), a monster gains `div_rand_round(speed * player_action_time, 10)` energy. The current [action threshold](../crawl-0.35/crawl-ref/source/monster.cc) is 80; action costs are typically around 10 but depend on action and creature. The queue selects the highest stored energy, executes an action, and may reinsert that monster. A bat can therefore act several times during one player decision. Keeping integer energy and randomized rounding is inexpensive and important.

The first scheduler should be a fixed-capacity version of the native heap, retaining its queue-update rules. For small actor sets, benchmark replacing it with a scan or warp reduction over eligible actors after each action. This removes heap manipulation and pointer chasing, but changes cost from approximately `A log M` to `A M` scalar work, or roughly `A (M/32 + log 32)` cooperative work. It is not automatically faster. Here `A` is the number of monster actions and `M` the actor capacity.

The [native comparator](../crawl-0.35/crawl-ref/source/mon-act.h) compares energy only. Equal-energy order comes from heap operations; choosing the smallest actor ID is not exact native behavior. A stable or seeded tie rank could be good enough, but test corridors, surround attacks, allies, and deaths specifically. Preserve just-summoned delays and effects that change another actor's energy. Resume an overlong world in another work chunk; do not cap its legal monster actions.

This source also has pursuit attacks and pursuit-related energy randomization in [mon-act.cc](../crawl-0.35/crawl-ref/source/mon-act.cc), with eligible pursuers marked in [movement.cc](../crawl-0.35/crawl-ref/source/movement.cc). These can materially change whether retreating is safe. They belong in the initial combat model, not a later cosmetic fidelity pass.

A conceptual step, omitting unsupported branches and presentation, is:

```text
validate and apply the explicitly selected player action
if the action consumed no time: return the resulting decision state
flush immediate effects at the native phase boundaries
apply relevant environment and player reactions; resolve noise
prepare monster energy, enchantments, and memory in native order
while an eligible monster remains:
    select the next scheduled monster
    resolve its action against the current world
    resolve its post-action and deferred effects
    update the schedule
resolve remaining noise, time, clouds, and post-monster reactions
update observation memory and termination state
```

The detailed implementation must follow the source's boundaries, including effects during monster preparation. This sketch is not a claim that all preparation can be reordered or performed simultaneously.

**Visibility can be compiled with little semantic loss.** Crawl already uses precomputed rays and ray-blocking bitsets in [los.cc](../crawl-0.35/crawl-ref/source/los.cc). Its definition allows appropriate rays between diagonally adjacent walls. Replacing it with one Bresenham ray per target would change visibility and shooting around corners.

For unchanged geometry, precompute visibility for each possible origin and relevant LOS mode. The maximum local window is 17 by 17: [defines.h](../crawl-0.35/crawl-ref/source/defines.h) gives maximum radius 8 and normal radius 7. At ten 32-bit words per origin, an 80 by 70 map costs 224,000 bytes per cached variant. Apply the appropriate range/shape mask; the whole square is not automatically visible. Different opacity modes and vision ranges require correct handling, not one universal visibility mask.

Doors, fog, terrain changes, and opaque actors prevent all LOS results from being permanently static. Precompute static blocked-ray masks while treating mutable blockers separately. At runtime add the current blockers and identify targets with at least one surviving native ray. Handle partial opacity as the source does: two half-opacity intersections can block a ray. Do not simply subtract cells from an initially closed-door visibility mask: opening a door can reveal cells that were absent from that mask.

Use cached complete visibility where its dependencies are unchanged, and a flattened local ray/bitset evaluator otherwise. This avoids enumerating all `2^door_count` door configurations. Preserve all necessary alternative rays; a single cached best ray is insufficient after blockers change. Cache invalidation can be local to affected origins within LOS range.

For projectiles, precompute the native candidate ray geometry and preference order. Walk the chosen ray through current terrain and occupancy, stopping or penetrating according to the effect. Native beam semantics are more than a visible/not-visible test. Treat reflection, explosions, clouds, and summoned projectiles as explicit supported effects rather than letting them enter an unbounded general beam interpreter.

**Monster navigation is a reasonable place to spend approximation error.** [mon-pathfind.cc](../crawl-0.35/crawl-ref/source/mon-pathfind.cc) implements A* with grid arrays and vector buckets; [try_pathfind](../crawl-0.35/crawl-ref/source/mon-movetarget.cc) manages waypoints, unreachable states, tracking limits, and fallback attack positions. This is monster AI work. Omitting auto-explore does not remove it.

Keep sleep, awareness, foe identity, last-known target, forgetting, fleeing, and bat behavior as explicit state. When a monster chooses a route, evaluate its eight neighbors with compiled topology data and current legality/occupancy checks. For a simple pursuing creature, prefer progress toward its remembered target, preserve relevant orthogonal/diagonal preferences, and randomize equivalent choices. This is a replacement for route selection, not a replacement for the entire AI with an omniscient chase rule.

Do not use geometric distance alone: it traps monsters at U-shaped obstacles. Do not route every monster toward the player's current hidden position: that changes information and pursuit behavior. Static shortest-path data can also make monsters more persistent and competent than native Crawl; keep native tracking cutoffs, unreachable/retry behavior, and target memory. Ordinary tracking ranges in this source are 3, 8, and 11 by intelligence, with exceptions.

For a small resident map set, all-pairs distances on traversable cells are straightforward. With 2,000 cells, 16-bit distances cost 8,000,000 bytes per map and movement profile; shortest-direction masks add 4,000,000 bytes if stored separately. Precompute separate movement/door capability profiles where needed. An alternative is a table indexed by origin and a bounded relative target offset, using native tracking limits; long-range allies and exceptional behavior need another path.

For a large map corpus, use local route tables or a portal graph and cached fields instead of keeping every all-pairs matrix resident. Dynamic doors, occupied corridors, clouds, and terrain changes require a bounded repair search or a resumable frontier calculation. Uniform-cost movement can use bitset BFS; weighted movement needs bucketed or weighted relaxation. Eight or sixteen relaxation passes are only a local approximation, not a solution for an arbitrarily winding level. Retain pending work or report the fallback; never confuse “not resolved yet” with unreachable.

Apply moves sequentially in scheduler order. Parallel destination proposals followed by collision arbitration can cause crowding, swapping, and blocking behavior to differ. Independent-world parallelism lets us avoid that approximation in the first implementation.

**Sound needs a spatial model, but perhaps not a full-grid simulation.** [shout.cc](../crawl-0.35/crawl-ref/source/shout.cc) propagates noise through a grid, with different attenuation for walls, doors, trees, and other features, plus attenuation for bends. Noise affects sleepers and can trigger additional noises. A Euclidean radius would change when nearby rooms join a fight.

Precompute acoustic transfer information for static geometry and evaluate each emitted sound at the current actor positions. With `E` sound events and `M` actors, this becomes roughly `E*M` lookups rather than a flood through the map for every world. Keep loudness, source identity, wakeup checks, and the phase in which newly generated sounds are processed.

Treat `heard_intensity = loudness - attenuation[source, listener]` as an approximation: native propagation includes direction history and competition between noise sources, so one pairwise scalar is not automatically equivalent. Calibrate against native single- and multi-source cases, optionally storing loudness-dependent transfers. Mutable doors and terrain need dependency-aware updates or a local propagation fallback. Give wakeup and reinforcement-arrival errors more weight than small intensity errors. Keep offscreen monsters active; freezing everything outside player LOS makes resting and exploration too safe.

**Keep combat random.** [attack.cc](../crawl-0.35/crawl-ref/source/attack.cc) contains modest integer calculations for hit tests, weapon and unarmed damage, modifiers, and armor. The surrounding game generality is the first thing to remove. Average damage would erase misses, kill thresholds, and the chance of dying before the next decision, which are central to D:1 choices.

Port the supported formulas and random rounding directly. Keep shields, brands, ranged attacks, constriction/escape, spell failure, MP use, buffs, relevant species effects, and level/skill progression in the coverage plan. [player-reacts.cc](../crawl-0.35/crawl-ref/source/player-reacts.cc) also shows HP/MP regeneration accumulators and the ordering of durations, constriction, and poison; preserve that ordering and elapsed action time.

If profiling shows an expensive repeated calculation for a small discrete state space, precompute conditional outcome distributions and sample them with a short CDF or alias table. Preserve the joint event distribution where damage and secondary effects are correlated. A table keyed only by attacker type and defender AC is not sufficient for general combat, and enumerating every inventory/status/skill combination would be counterproductive.

Use per-world native PCG state initially. It is already small and avoids global contention once each world owns its state. A later alternative is counter-based Philox keyed by episode, rollout sample, actor identity, action occurrence, effect kind, and draw index. NVIDIA documents [Philox device generation](https://docs.nvidia.com/cuda/curand/device-api-overview.html). This can simplify branching and replay, but is not native seed-for-seed reproduction. Preserve unbiased integer sampling and distinguish actor slot reuse from actor identity.

Precomputed random tapes are also possible, provided worlds have independent identities and consume draws according to their own events. Reusing one shared draw across worlds would correlate training samples. For candidate-action comparisons, deliberately paired randomness can reduce variance, but corresponding events need semantic keys; pairing the nth RNG call across diverging branches does not align the same event.

**Batching is the central performance choice.** Build two kernel mappings over the same compact rules:

| Mapping | Useful property | Main risk |
|---|---|---|
| One thread per world | Simple serial semantics; many simultaneous worlds; a useful baseline | Different actions, paths, and monster counts cause warp divergence and scattered accesses. |
| One warp per world | Lanes cooperate on actor scans, LOS, masks, and observations; different worlds branch independently | Scalar action resolution leaves lanes idle; reductions and synchronization can cost more than the saved work. |

My initial candidate is a thread-per-world baseline, then a warp-per-world version for worlds where cooperative scans matter. Compare both at realistic actor counts. Do not assume a whole block per world is useful for a small D:1 state. Cohort worlds by rule profile and capacity; optionally group action types when sorting/permutation overhead is justified. NVIDIA's [CUDA best-practices guide](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html) supports keeping data on the device and arranging adjacent-thread accesses to coalesce. It does not establish which of these mappings wins for Crawl.

One transition launch should perform a full player decision and its world reactions, rather than launching a separate kernel for every monster action. Keep observations and the policy on the GPU and pass arrays directly between them. Do not copy every state to Python or the CPU after every move. Batched inference still runs at each decision that requires it; fusing an entire rollout is appropriate only when its policy can also execute there. Fixed-shape step/inference sequences can use graph capture after correctness is established.

For training, a candidate sweep is 1,024, 4,096, 16,384, and 32,768 concurrent worlds, with asynchronous episode resets from resident templates. Those are benchmark batch sizes, not a throughput prediction. Sharing maps between worlds helps cache locality but also correlates experience; split evaluation by unseen map seeds and vault families, not just combat RNG seeds.

For action evaluation, flatten `(root position, candidate action, sample)` into the world dimension. For example, 16 candidate actions with 2,048 samples each give 32,768 rollout worlds from one root. Share immutable map data and copy compact mutable state, run a continuation policy, and reduce returns by candidate. This fits GPU parallelism better than a first implementation built around a dynamically allocated, concurrently updated search tree. A small candidate set with no additional sampling will not saturate the GPU.

**The memory budget looks plausible, with topology tables as a major variable.** These are illustrative sizes, not measured D:1 averages. Native map bounds are 80 by 70; the example traversable-cell count is an assumption.

| Allocation | Assumption | Size |
|---|---|---:|
| Static local visibility | 5,600 origins, ten 32-bit words, one variant | 0.214 MiB/map |
| All-pairs navigation distances | 2,000 cells, 16 bits, one movement profile | 7.629 MiB/map |
| Optional shortest-direction masks | 2,000 cells, 8 bits | 3.815 MiB/map |
| Resident navigation distances | 64 such maps, one movement profile | 488.281 MiB |
| Mutable state | 32,768 worlds at a hypothetical 16 KiB/world | 512 MiB |
| Full-grid occupancy, if additional | 32,768 worlds, 5,600 signed 16-bit cells | 350 MiB |

Avoid double-counting occupancy if it is already included in the mutable-state estimate. Full-grid all-pairs distances would cost 59.814 MiB/map/profile; many map and movement variants can dominate memory. Policy weights, activations, observations, rollout storage, and temporary workspaces need their own budget. A local observation plus sparse actor/item lists is preferable to repeatedly materializing large dense feature planes for every whole level.

**The decision interface should expose game actions directly.** A record such as `(verb, direction_or_cell, inventory_slot, spell_or_ability_id)` handles movement/bump attack, explicit melee or reach attacks, wait, open/close, pickup/drop/equip, fire/throw, cast/evoke, quaff/read, and stairs. Target selection belongs to the agent. Any learning/training or equipment configuration decisions must be either exposed explicitly or stated as fixed scenario policy; omitting auto-explore and tab does not remove them.

Maintain true world state separately from the observation and its remembered terrain/items/monsters. Precomputed geometry is simulator data, not automatically policy input. Action masks must not reveal hidden enemies, unidentified items, or undiscovered terrain by consulting privileged truth. Mirror native time consumption for invalid or interrupted actions. End the D:1 episode at the chosen native exit event, death, or an explicit time limit; keep truncation distinct from death. If later adding multi-turn actions or variable-duration discounting, account for elapsed game time rather than treating every decision as an equal time step.

**“Good enough” should be measured by decisions and transfer.** Use the native engine as an offline reference and evaluation environment, not as a synchronous callback for routine GPU steps. Native-to-compact state export is the first useful integration boundary. A full compact-to-native importer is extra work; early comparisons can instead replay native action prefixes to create paired starting states.

Run deterministic checks for geometry, action legality/time, effect ordering, state invariants, and cloned-state independence. Where implementation and RNG order are intentionally identical, compare individual transitions. Once route choices or RNG streams change, use distributional comparisons; matching seeds no longer means matching trajectories.

Use combat scenarios that probe actual decisions: retreat versus attack under pursuit rules, a bat's extra actions, a python constriction escape, a dart slug behind another actor, a kobold with stones, a gnoll weapon, doors and diagonal corners, sleeping reinforcements, and spells/summons from the supported starts. Compare death probability, damage tails, time to kill, target/position distributions, first contact, and wakeup/arrival timing. Include several-monster fights, not only isolated duels.

Most importantly, choose actions using the approximate simulator, then evaluate those actions and trained policies in native Crawl. Measure action-ranking regret under the intended return and native D:1 completion/survival, alongside consumable use and exploration behavior. High one-step agreement on quiet turns can hide a large error in rare lethal states. Set explicit error tolerances and confidence intervals before tuning approximations, stratify rare mechanics, and publish unsupported/overflow rates with the result.

Benchmark four stages: native headless Crawl, the compact simulator on CPU, the same compact rules on GPU, and then each additional approximation. This separates gains from removing general engine overhead from gains due to the GPU. Include all-core CPU throughput, realistic mixtures of quiet/exploration/combat states, reset costs, and observation/policy inference. Report both environment transitions per second and useful evaluated decisions per second, plus latency at small batch sizes. There is no justified numerical speedup claim before that measurement.

**The implementation order I would use is:**

1. Build the native scenario/state exporter and content manifest. Produce normal and exceptional D:1 corpora; capture exact terrain, gear, initial energy, hidden state, and rule profile. Leave native gameplay untouched.
2. Implement the compact CPU rules for a declared initial player profile and ordinary D:1 monsters, including their ranged/special actions, pursuit, doors, awareness, and timing. This is the semantic baseline, not a claim of all-start D:1 support.
3. Compile native visibility/ray tables and static navigation data. Add dynamic-blocker handling and explicit capacity/unsupported results. Establish transition and distribution comparisons against native Crawl.
4. Implement both GPU world mappings, keep state and observations on-device, and benchmark the crossover against the compact CPU implementation. Stop expanding GPU work if this slice does not provide useful end-to-end throughput.
5. Introduce navigation and acoustic approximations individually, accepting them based on native decision quality and measured speed. Preserve the previous implementation as a comparison mode.
6. Expand the manifest's supported closure through player starts, loot, brands, consumables, spells, allies, and exceptional vault effects. Batch exceptional supported rules separately where that improves performance. Keep unsupported scenarios visible until coverage is complete.

The recommendation is to preserve the stochastic tactical game while changing its representation and execution model. Precomputed content, fixed arrays, shared geometry, and parallel worlds provide the first opportunity. Approximate route selection and acoustics where measurements justify it. Simultaneous monster turns, average damage, frozen offscreen monsters, and geometric-only navigation would buy simplicity at the cost of teaching substantially different decisions.
